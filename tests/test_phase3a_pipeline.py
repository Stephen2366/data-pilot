"""Phase 3A M11 新 Text2SQL Pipeline 与 trace_steps 测试。

★ M11 的 seam 选在 `/api/query` 和 JSONL trace：前者保证真实 API 调用能强制绕过模板，
后者保证评测可以看到 schema_retrieval、query_plan、SQL Guard 等分步骤证据。
"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from eval.run_eval import EvalCase, run_cases
from scripts.seed_data import seed_database


@contextmanager
def _seeded_test_client(trace_path: Path) -> Generator[TestClient, None, None]:
    """创建带 seed 数据和独立 trace 文件的测试客户端。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)

    def override_get_db() -> Generator[Session, None, None]:
        """把正式数据库 Session 替换成当前测试独享的内存库。"""

        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "trace_path"):
            delattr(app.state, "trace_path")
        Base.metadata.drop_all(engine)


class _FakeM11LLMClient:
    """按 prompt 类型返回固定 QueryPlan / SQL，避免测试消耗真实 LLM。"""

    def complete(self, *, prompt: str) -> str:
        if "QueryPlan JSON Schema" in prompt:
            return json.dumps(
                {
                    "steps": [
                        {
                            "step_id": "step_1",
                            "step_index": 1,
                            "step_type": "sql_query",
                            "purpose": "按渠道统计订单量。",
                            "depends_on": [],
                            "task_type": "aggregation",
                            "tables": ["channels", "orders"],
                            "columns": ["channels.channel_name", "orders.id", "orders.channel_id"],
                            "metrics": ["order_count"],
                            "filters": [],
                            "joins": ["orders_channel"],
                            "aggregations": ["COUNT(orders.id)"],
                            "group_by": ["channels.channel_name"],
                            "order_by": ["order_count DESC", "channels.channel_name ASC"],
                            "limit": None,
                            "output_columns": ["channels.channel_name", "order_count"],
                            "output_expressions": {"order_count": "COUNT(orders.id)"},
                        }
                    ]
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "sql": """
SELECT
  c.channel_name,
  COUNT(o.id) AS order_count
FROM channels c
JOIN orders o ON o.channel_id = c.id
GROUP BY c.id, c.channel_name
ORDER BY order_count DESC, c.channel_name ASC
""".strip(),
                "tables_used": ["channels", "orders"],
                "confidence": 0.9,
                "reasoning_summary": "使用局部 Schema 中的 orders_channel 关系按渠道聚合订单量。",
            },
            ensure_ascii=False,
        )


class _FakeDangerousSQLClient(_FakeM11LLMClient):
    """复用合法 QueryPlan，但在 SQL 生成阶段故意返回危险语句。"""

    def complete(self, *, prompt: str) -> str:
        if "QueryPlan JSON Schema" in prompt:
            return super().complete(prompt=prompt)
        return json.dumps(
            {
                "sql": "DELETE FROM orders",
                "tables_used": ["orders"],
                "confidence": 0.1,
                "reasoning_summary": "故意构造危险 SQL，验证 M11 仍走 SQL Guard。",
            },
            ensure_ascii=False,
        )


class _FakeBrokenSQLClient(_FakeM11LLMClient):
    """QueryPlan 正常，但 SQL 生成阶段返回不可解析文本，用来验证失败 trace。"""

    def complete(self, *, prompt: str) -> str:
        if "QueryPlan JSON Schema" in prompt:
            return super().complete(prompt=prompt)
        return "我无法稳定返回 JSON，也没有 SELECT。"


class _FakeExtraProjectionClient(_FakeM11LLMClient):
    """计划只要两列，SQL 故意额外输出 channel_code，验证精确投影在执行前阻断。"""

    def complete(self, *, prompt: str) -> str:
        if "QueryPlan JSON Schema" in prompt:
            return super().complete(prompt=prompt)
        return json.dumps(
            {
                "sql": """
SELECT
  c.channel_name,
  COUNT(o.id) AS order_count,
  c.channel_code
FROM channels c
JOIN orders o ON o.channel_id = c.id
GROUP BY c.id, c.channel_name, c.channel_code
ORDER BY order_count DESC, c.channel_name ASC
""".strip(),
                "tables_used": ["channels", "orders"],
                "confidence": 0.9,
                "reasoning_summary": "故意增加计划外投影。",
            },
            ensure_ascii=False,
        )


def _patch_m11_llm(monkeypatch) -> None:
    """让 M11 pipeline 复用同一个 fake client 完成 plan 与 SQL 两次调用。"""

    from engine.nl2sql import pipeline as text2sql_pipeline

    fake_client = _FakeM11LLMClient()
    monkeypatch.setattr(text2sql_pipeline, "get_default_llm_client", lambda: fake_client)


def test_force_new_pipeline_bypasses_template_and_writes_required_trace_steps(tmp_path: Path, monkeypatch) -> None:
    """模板可命中的问题在强制新链路时也必须走 M11 pipeline，并写完整 trace_steps。"""

    _patch_m11_llm(monkeypatch)
    trace_path = tmp_path / "m11-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": True},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    step_names = [step["name"] for step in trace["trace_steps"]]
    retrieval_step = next(step for step in trace["trace_steps"] if step["name"] == "schema_retrieval")
    sql_generation_step = next(step for step in trace["trace_steps"] if step["name"] == "sql_generation")

    assert response.status_code == 200
    assert body["safety_status"] == "passed"
    assert body["sql"].startswith("SELECT\n  c.channel_name")
    assert body["tables_used"] == ["channels", "orders"]
    assert step_names[:8] == [
        "schema_retrieval",
        "schema_context",
        "join_path",
        "query_plan",
        "plan_validation",
        "sql_generation",
        "sql_guard",
        "sql_execution",
    ]
    assert all(step["step_index"] == index for index, step in enumerate(trace["trace_steps"], start=1))
    assert trace["trace_steps"][7]["step_type"] == "sql_query"
    assert trace["trace_steps"][7]["metadata"]["row_count"] == len(body["rows"])
    assert trace["trace_steps"][7]["metadata"]["column_count"] == len(body["columns"])
    assert "metric_doc_hits" in retrieval_step["metadata"]
    assert sql_generation_step["metadata"]["plan_step_tables"] == ["channels", "orders"]
    assert sql_generation_step["metadata"]["plan_step_columns"] == [
        "channels.channel_name",
        "orders.id",
        "orders.channel_id",
    ]
    assert sql_generation_step["metadata"]["plan_step_filters"] == []
    assert sql_generation_step["metadata"]["plan_step_metrics"] == ["order_count"]
    assert sql_generation_step["metadata"]["plan_step_joins"] == ["orders_channel"]
    assert sql_generation_step["metadata"]["plan_step_output_columns"] == ["channels.channel_name", "order_count"]
    assert sql_generation_step["metadata"]["contract_status"] == "passed"
    assert sql_generation_step["metadata"]["candidate_sql"] == body["sql"]
    assert sql_generation_step["metadata"]["query_plan_step"]["step_id"] == "step_1"
    output_step = next(step for step in trace["trace_steps"] if step["name"] == "output_projection")
    assert output_step["status"] == "success"
    assert output_step["metadata"]["expected_columns"] == body["columns"]
    assert trace["trace_steps"][-1]["name"] == "chart_generation"
    assert trace["langfuse_span_mode"] == "live"
    assert trace["langfuse_write_status"] == "skipped"


def test_new_pipeline_generated_sql_still_goes_through_sql_guard(tmp_path: Path, monkeypatch) -> None:
    """即使新 pipeline 的 LLM 返回危险 SQL，也必须由 `run_sql_tool()` 统一拦截。"""

    from engine.nl2sql import pipeline as text2sql_pipeline

    monkeypatch.setattr(text2sql_pipeline, "get_default_llm_client", lambda: _FakeDangerousSQLClient())
    trace_path = tmp_path / "guard-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": True},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    guard_step = next(step for step in trace["trace_steps"] if step["name"] == "sql_guard")

    assert response.status_code == 200
    assert body["safety_status"] == "blocked"
    assert body["error_type"] == "sql_guard_blocked"
    assert body["tool_calls"][0]["tool_name"] == "sql_guard"
    assert guard_step["status"] == "blocked"
    sql_generation_step = next(step for step in trace["trace_steps"] if step["name"] == "sql_generation")
    assert sql_generation_step["metadata"]["sql_guard_precheck_status"] == "blocked"
    assert not any(step["name"] == "sql_execution" for step in trace["trace_steps"])


def test_pipeline_blocks_extra_projection_before_sql_execution(tmp_path: Path, monkeypatch) -> None:
    """精确投影属于 QueryPlan→SQL fidelity；额外非敏感列也不能静默执行。"""

    from engine.nl2sql import pipeline as text2sql_pipeline

    monkeypatch.setattr(text2sql_pipeline, "get_default_llm_client", lambda: _FakeExtraProjectionClient())
    trace_path = tmp_path / "projection-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": True},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    generation_step = next(step for step in trace["trace_steps"] if step["name"] == "sql_generation")

    assert response.status_code == 200
    assert body["safety_status"] == "blocked"
    assert body["error_type"] == "output_projection_contract_failed"
    assert generation_step["metadata"]["reason_code"] == "projection_set_mismatch"
    assert generation_step["metadata"]["candidate_sql"].startswith("SELECT")
    assert generation_step["metadata"]["sql_guard_precheck_status"] == "passed"
    assert not any(step["name"] == "sql_execution" for step in trace["trace_steps"])


def test_default_query_uses_new_pipeline_and_writes_trace_steps(tmp_path: Path, monkeypatch) -> None:
    """普通 API 不传开关时默认进入新 pipeline，而不是静默回到模板路径。"""

    _patch_m11_llm(monkeypatch)
    trace_path = tmp_path / "default-new-pipeline-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops"},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())

    assert response.status_code == 200
    assert body["sql"].startswith("SELECT\n  c.channel_name")
    assert [step["name"] for step in trace["trace_steps"]][:4] == [
        "schema_retrieval", "schema_context", "join_path", "query_plan",
    ]


def test_explicit_false_keeps_legacy_baseline_for_compatibility(tmp_path: Path, monkeypatch) -> None:
    """旧路径只在调用方明确传 false 时保留，方便兼容排障。"""

    _patch_m11_llm(monkeypatch)
    trace_path = tmp_path / "explicit-baseline-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": False},
        )

    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())

    assert response.status_code == 200
    assert "trace_steps" not in trace or trace["trace_steps"] == []


def test_query_can_request_milvus_qwen_embedding_profile_for_new_pipeline(tmp_path: Path, monkeypatch) -> None:
    """演示页按钮传入的 profile 必须进入 schema retrieval，而不是只停留在前端。"""

    from engine.nl2sql import pipeline as text2sql_pipeline

    _patch_m11_llm(monkeypatch)
    original_retrieve_schema = text2sql_pipeline.retrieve_schema
    calls: dict[str, object] = {}

    def wrapped_retrieve_schema(**kwargs):
        calls["schema_retrieval_profile"] = kwargs.get("schema_retrieval_profile")
        kwargs["schema_retrieval_profile"] = "default"
        return original_retrieve_schema(**kwargs)

    monkeypatch.setattr(text2sql_pipeline, "retrieve_schema", wrapped_retrieve_schema)
    trace_path = tmp_path / "retrieval-profile-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={
                "question": "各渠道订单量是多少？",
                "user_role": "ops",
                "force_new_pipeline": True,
                "schema_retrieval_profile": "milvus_qwen37",
            },
        )

    assert response.status_code == 200
    assert calls["schema_retrieval_profile"] == "milvus_qwen37"


def test_eval_new_text2sql_mode_sends_force_flag_and_records_actual_mode(tmp_path: Path, monkeypatch) -> None:
    """eval 的 `pipeline_mode=new_text2sql` 要真正触发新链路，而不是只改报告字段。"""

    _patch_m11_llm(monkeypatch)
    trace_path = tmp_path / "eval-new-pipeline-traces.jsonl"
    case = EvalCase(
        case_id="m11_eval_force_new",
        task_type="aggregation",
        question="各渠道订单量是多少？",
        user_role="ops",
        expected_tables=["channels", "orders"],
        expected_columns=["channel_name", "order_count"],
        expected_metrics=["order_count"],
        expected_trace_steps=["schema_retrieval", "query_plan", "sql_execution"],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="contains",
        check_value="order_count",
    )

    with _seeded_test_client(trace_path) as client:
        results = run_cases([case], client)

    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())

    assert results[0].actual_pipeline_mode == "new_text2sql"
    assert results[0].passed
    assert any(step["name"] == "query_plan" for step in trace["trace_steps"])


def test_sql_generation_failure_trace_keeps_raw_preview_and_parse_context(tmp_path: Path, monkeypatch) -> None:
    """LLM 解析失败要把 raw preview / parse error / prompt length 写进 trace metadata。"""

    from engine.nl2sql import pipeline as text2sql_pipeline

    monkeypatch.setattr(text2sql_pipeline, "get_default_llm_client", lambda: _FakeBrokenSQLClient())
    trace_path = tmp_path / "broken-sql-generation-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": True},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    sql_generation_step = next(step for step in trace["trace_steps"] if step["name"] == "sql_generation")

    assert response.status_code == 200
    assert body["safety_status"] == "passed"
    assert body["error_type"] == "llm_generation_error"
    assert body["execution_status"] == "external_unavailable"
    assert body["blocked_reason"] is None
    assert sql_generation_step["status"] == "error"
    assert sql_generation_step["metadata"]["stage"] == "sql_generation"
    assert sql_generation_step["metadata"]["raw_response_preview"] == "我无法稳定返回 JSON，也没有 SELECT。"
    assert "无法从 LLM 输出中提取 SQL" in sql_generation_step["metadata"]["parse_error"]
    assert sql_generation_step["metadata"]["prompt_length"] > 100
