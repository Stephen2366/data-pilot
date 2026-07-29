"""M17 scorer 分层与 LangFuse Score 回写测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import Settings
from eval.run_eval import EvalCase, EvalResult, _score_case
from eval.scorers.base import EvalScoreDetail, LangFuseScorePayload
from eval.scorers.factory import score_case
from eval.scorers.langfuse_scores import LangFuseScoreWriter, build_langfuse_score_payloads
from eval.scorers.llm_judge import resolve_judge_model
from eval.scorers.rule_scorers import score_case_rules


def _case(**overrides: Any) -> EvalCase:
    """构造最小 EvalCase，单测只覆盖 M17 scorer 关心的字段。"""

    data = {
        "case_id": "m17_case",
        "task_type": "aggregation",
        "question": "各渠道订单量是多少？",
        "user_role": "ops",
        "expected_tables": ["orders", "channels"],
        "expected_columns": ["channel_name", "order_count"],
        "expected_metrics": ["order_count"],
        "expected_trace_steps": [],
        "pipeline_mode": "new_text2sql",
        "security_expectation": "allow",
        "check_type": "contains",
        "check_value": "Mobile App",
    }
    data.update(overrides)
    return EvalCase(**data)


def _body() -> dict[str, Any]:
    """构造最小通过响应体。"""

    return {
        "route": "sql",
        "answer": "新 Text2SQL 查询结果：channel_name=Mobile App，order_count=650",
        "safety_status": "passed",
        "tables_used": ["orders", "channels"],
        "columns": ["channel_name", "order_count"],
        "rows": [{"channel_name": "Mobile App", "order_count": 650}],
        "cost": {"latency_ms": 10.0},
        "trace_id": "datapilot-trace-1",
    }


def test_rule_scorers_emit_details_without_changing_legacy_summary() -> None:
    """规则 scorer 要产出多条 detail，但 `_score_case()` 汇总结果保持旧行为。"""

    case = _case()
    body = _body()

    details = score_case_rules(case=case, body=body, status_code=200, actual_pipeline_mode="new_text2sql")
    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert [detail.name for detail in details] == [
        "rule:safety_compliance",
        "rule:table_hit",
        "rule:column_recall",
        "rule:sql_success",
        "rule:latency_p95",
        "rule:contains",
    ]
    assert next(detail for detail in details if detail.name == "rule:latency_p95").passed is None
    assert score.passed is True
    assert score.reason == "ok"


def test_score_case_factory_adds_llm_correctness_when_judge_model_is_explicit() -> None:
    """只有显式传 judge model 时才追加 `llm:correctness`。"""

    class FakeJudgeClient:
        """模拟 judge 模型返回 JSON 分数。"""

        def complete(self, *, prompt: str, system_prompt: str | None = None) -> str:
            return json.dumps({"score": 0.9, "reason": "answer matches reference"}, ensure_ascii=False)

    details = score_case(
        case=_case(),
        body=_body(),
        status_code=200,
        actual_pipeline_mode="new_text2sql",
        judge_model="fake-judge",
        judge_client=FakeJudgeClient(),
    )

    correctness = details[-1]
    assert correctness.name == "llm:correctness"
    assert correctness.value == 0.9
    assert correctness.passed is True


def test_resolve_judge_model_prefers_cli_over_settings() -> None:
    """judge model 优先级固定为 CLI > EVAL_JUDGE_MODEL > 空。"""

    settings = Settings(_env_file=None, EVAL_JUDGE_MODEL="env-judge")

    assert resolve_judge_model("cli-judge", settings) == "cli-judge"
    assert resolve_judge_model("", settings) == "env-judge"
    assert resolve_judge_model("", Settings(_env_file=None, EVAL_JUDGE_MODEL="")) == ""


def test_build_langfuse_score_payloads_uses_jsonl_trace_mapping(tmp_path: Path) -> None:
    """Score 回写按 JSONL 中的 `langfuse_trace_id` 关联，不查 Cloud trace 可见性。"""

    trace_path = tmp_path / "traces.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "trace_id": "datapilot-trace-1",
                "langfuse_trace_id": "lf-trace-1",
                "langfuse_span_mode": "live",
            }
        ),
        encoding="utf-8",
    )
    result = EvalResult(
        case=_case(),
        passed=True,
        reason="ok",
        issue_tags=[],
        review_required=False,
        skipped_due_to_pipeline_mode=False,
        status_code=200,
        route="sql",
        safety_status="passed",
        error_type=None,
        trace_id="datapilot-trace-1",
        sql="SELECT 1",
        response_body=_body(),
        actual_pipeline_mode="new_text2sql",
        score_details=[
            EvalScoreDetail(name="rule:table_hit", value=1.0, passed=True, reason="table_hit_ok"),
            EvalScoreDetail(name="llm:correctness", value=None, skipped=True, reason="judge_disabled"),
        ],
    )

    payloads = build_langfuse_score_payloads(results=[result], trace_path=trace_path)

    assert len(payloads) == 1
    assert payloads[0].trace_id == "lf-trace-1"
    assert payloads[0].name == "rule:table_hit"
    assert payloads[0].metadata["case_id"] == "m17_case"


def test_langfuse_score_writer_degrades_when_disabled() -> None:
    """LangFuse 默认关闭时，score writer 只记 skipped，不 import SDK / 不报错。"""

    writer = LangFuseScoreWriter(Settings(_env_file=None, LANGFUSE_ENABLED="false"))

    result = writer.write_scores([])
    skipped = writer.write_scores(
        [
            LangFuseScorePayload(trace_id="lf-trace-1", name="rule:table_hit", value=1.0),
        ]
    )

    assert result == {"ok": 0, "skipped": 0, "failed": 0}
    assert skipped == {"ok": 0, "skipped": 1, "failed": 0}


def test_langfuse_score_writer_calls_sdk_create_score_and_flushes() -> None:
    """LangFuse 启用时，writer 按 trace_id 调 create_score 后 flush。"""

    class FakeScoreClient:
        """记录 create_score / flush 调用，避免访问真实 Cloud。"""

        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.scores: list[dict[str, Any]] = []
            self.flushed = False

        def create_score(self, **kwargs: Any) -> None:
            self.scores.append(kwargs)

        def flush(self) -> None:
            self.flushed = True

    class FakeFactory:
        """保存最近一次 fake client。"""

        def __init__(self) -> None:
            self.client: FakeScoreClient | None = None

        def __call__(self, **kwargs: Any) -> FakeScoreClient:
            self.client = FakeScoreClient(**kwargs)
            return self.client

    factory = FakeFactory()
    writer = LangFuseScoreWriter(
        Settings(
            _env_file=None,
            LANGFUSE_ENABLED="true",
            LANGFUSE_PUBLIC_KEY="pk-test",
            LANGFUSE_SECRET_KEY="sk-test",
            LANGFUSE_BASE_URL="http://localhost:3000",
        ),
        client_factory=factory,
    )

    result = writer.write_scores([LangFuseScorePayload(trace_id="lf-trace-1", name="rule:table_hit", value=1.0)])

    assert result == {"ok": 1, "skipped": 0, "failed": 0}
    assert factory.client is not None
    assert factory.client.flushed is True
    assert factory.client.scores[0]["trace_id"] == "lf-trace-1"
    assert factory.client.scores[0]["name"] == "rule:table_hit"
    assert factory.client.scores[0]["data_type"] == "NUMERIC"
