"""M27 RunEnvironment：唯一拥有 SQLite snapshot 与 FastAPI 注入生命周期的 module。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from eval.contracts import EvalRunSpec, ResolvedRuntimeIdentity
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import build_schema_documents, schema_documents_hash
from scripts.seed_data import seed_database


class SQLiteRunEnvironmentFactory:
    """默认 SQLite oracle 环境 factory。

    同一 engine 同时注入 API 与 OraclePort，因此候选请求与 reference SQL 观察的是同一个
    确定性 snapshot。它不改动模型、检索或 retry 默认值，只记录当前 resolved 设置。
    """

    def __init__(self, *, trace_root: Path) -> None:
        self._trace_root = trace_root

    def create(self, run_spec: EvalRunSpec) -> "SQLiteRunEnvironment":
        """解析当前默认配置并先完成显式 requested/resolved 对账。"""
        settings = get_settings()
        values = _resolved_runtime_values(settings, run_spec)
        mismatches = {key: (expected, values.get(key)) for key, expected in run_spec.requested_runtime_constraints.items() if values.get(key) != expected}
        if mismatches:
            raise ValueError(f"requested/resolved runtime mismatch: {mismatches}")
        return SQLiteRunEnvironment(trace_path=self._trace_root / f"{run_spec.run_id}.jsonl", resolved_runtime_identity=ResolvedRuntimeIdentity(values))


def _resolved_runtime_values(settings: Any, run_spec: EvalRunSpec) -> dict[str, Any]:
    """冻结本轮实际会影响 Schema Retrieval 可比性的配置与语料指纹。

    M27 artifact 过去只记录 backend/provider，无法区分“同为 Milvus 但 collection、embedding
    模型或 schema 文档不同”的两轮运行。这里不创建 Milvus 连接、不写 collection，只读取
    已解析的 Settings 和本地 domain pack，作为运行开始前的 resolved runtime identity。
    """

    embedding_provider = settings.schema_embedding_provider.lower()
    if embedding_provider in {"dashscope", "qwen"}:
        embedding_model = settings.qwen_embedding_model
        embedding_dimensions: int | None = settings.qwen_embedding_dimensions
    elif embedding_provider == "siliconflow":
        embedding_model = settings.siliconflow_embedding_model
        embedding_dimensions = settings.siliconflow_embedding_dimensions
    else:
        embedding_model = None
        embedding_dimensions = None

    schema_documents = build_schema_documents(load_domain_schema())
    values: dict[str, Any] = {
            "llm_provider": settings.llm_provider,
            "llm_model": settings.qwen_model if settings.llm_provider.lower() == "qwen" else settings.llm_model,
            "pipeline_mode": run_spec.execution_protocol.pipeline_mode,
            "schema_vector_backend": settings.schema_vector_backend,
            "schema_embedding_provider": embedding_provider,
            "schema_embedding_model": embedding_model,
            "schema_embedding_dimensions": embedding_dimensions,
            "milvus_collection": settings.milvus_collection if settings.schema_vector_backend.lower() == "milvus" else None,
            "schema_docs_count": len(schema_documents),
            "schema_docs_hash": schema_documents_hash(schema_documents),
            "schema_fusion_strategy": run_spec.execution_protocol.schema_fusion_strategy,
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "llm_max_retries": settings.llm_max_retries,
            "llm_retry_backoff_seconds": settings.llm_retry_backoff_seconds,
            "oracle_fixture_identity": run_spec.oracle_fixture_identity,
        }
    return values


class SQLiteRunEnvironment:
    """真实 FastAPI/TestClient + SQLite snapshot 的 RunEnvironment adapter。"""

    def __init__(self, *, trace_path: Path, resolved_runtime_identity: ResolvedRuntimeIdentity) -> None:
        self.resolved_runtime_identity = resolved_runtime_identity
        self._trace_path = trace_path
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)
        self._trace_path.write_text("", encoding="utf-8")
        self._engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self._engine)
        with Session(self._engine) as session:
            seed_database(session, reset_existing=True)

        def override_get_db():
            with Session(self._engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        app.state.trace_path = self._trace_path
        self._client = TestClient(app)
        self.pipeline = _FastApiPipelinePort(self._client, self._trace_path)
        self.oracle = _SQLiteOraclePort(self._engine)

    def close(self) -> None:
        """撤销 FastAPI override 并释放本轮专属 SQLite snapshot。"""
        app.dependency_overrides.clear()
        if hasattr(app.state, "trace_path"):
            delattr(app.state, "trace_path")
        Base.metadata.drop_all(self._engine)
        self._engine.dispose()


class _FastApiPipelinePort:
    def __init__(self, client: TestClient, trace_path: Path) -> None:
        self._client = client
        self._trace_path = trace_path

    def execute(self, *, question: str, user_role: str, pipeline_mode: str, fusion_strategy: str) -> tuple[int, dict[str, Any], tuple[dict[str, Any], ...]]:
        """通过真实 API seam 执行一次请求，并按 trace_id 取回唯一 trace。"""
        # API 默认已经切到新 pipeline；Eval 仍需显式写出两条路径，才能让 legacy baseline
        # 读取保留的历史合同，而不是因为“省略字段”意外走到新链路。
        payload: dict[str, Any] = {
            "question": question,
            "user_role": user_role,
            "force_new_pipeline": pipeline_mode != "baseline",
        }
        if pipeline_mode != "baseline":
            payload["schema_fusion_strategy"] = fusion_strategy
        response = self._client.post("/api/query", json=payload)
        body = response.json()
        trace_id = body.get("trace_id")
        for raw in reversed(self._trace_path.read_text(encoding="utf-8").splitlines()):
            if raw.strip():
                record = json.loads(raw)
                if record.get("trace_id") == trace_id:
                    return response.status_code, body, tuple(record.get("trace_steps") or [])
        return response.status_code, body, ()


class _SQLiteOraclePort:
    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def execute(self, reference_sql: str) -> tuple[dict[str, Any], ...]:
        """在与候选 API 共用的 engine 上读取 deterministic oracle rows。"""
        with Session(self._engine) as session:
            result = session.execute(text(reference_sql))
            return tuple(dict(row) for row in result.mappings().all())
