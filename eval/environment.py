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
        values: dict[str, Any] = {
            "llm_provider": settings.llm_provider,
            "llm_model": settings.qwen_model if settings.llm_provider.lower() == "qwen" else settings.llm_model,
            "pipeline_mode": run_spec.execution_protocol.pipeline_mode,
            "schema_vector_backend": settings.schema_vector_backend,
            "schema_embedding_provider": settings.schema_embedding_provider,
            "schema_fusion_strategy": run_spec.execution_protocol.schema_fusion_strategy,
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "llm_max_retries": settings.llm_max_retries,
            "llm_retry_backoff_seconds": settings.llm_retry_backoff_seconds,
            "oracle_fixture_identity": run_spec.oracle_fixture_identity,
        }
        mismatches = {key: (expected, values.get(key)) for key, expected in run_spec.requested_runtime_constraints.items() if values.get(key) != expected}
        if mismatches:
            raise ValueError(f"requested/resolved runtime mismatch: {mismatches}")
        return SQLiteRunEnvironment(trace_path=self._trace_root / f"{run_spec.run_id}.jsonl", resolved_runtime_identity=ResolvedRuntimeIdentity(values))


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
        payload: dict[str, Any] = {"question": question, "user_role": user_role}
        if pipeline_mode != "baseline":
            payload.update({"force_new_pipeline": True, "schema_fusion_strategy": fusion_strategy})
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
