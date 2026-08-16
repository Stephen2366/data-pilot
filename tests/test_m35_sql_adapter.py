"""M35 SQL adapter 四轴与 Evidence 接线测试。"""

from __future__ import annotations

from app.schemas.agent import ToolCallTrace
from engine.governance import demo_caller
from engine.harness.adapters import _sql_observation
from engine.harness.contracts import HarnessRequest
from engine.tools.sql_tool import SQLToolResult


def _request() -> HarnessRequest:
    """构造已解析 active role 的 SQL Tool 输入。"""

    return HarnessRequest(
        question="各渠道订单量是多少？",
        run_id="m35-sql-adapter",
        caller=demo_caller(caller_id="m35-sql", roles=("ops",)),
        active_sql_role="ops",
    )


def test_guard_blocked_is_safety_blocked_without_sql_evidence() -> None:
    """Guard 是安全裁决，不得生成 SQL Evidence 或伪装为技术不可用。"""

    observation = _sql_observation(
        request=_request(), sql="DROP TABLE orders", answer_hint="x", tool_result=None,
        error_type="sql_guard_blocked", message="只允许 SELECT",
    )

    assert (observation.execution_status, observation.safety_status, observation.answer_status) == (
        "completed", "blocked", "no_answer"
    )
    assert observation.evidence_refs == ()
    assert observation.blocked_reason == "只允许 SELECT"


def test_sql_execution_error_is_not_mislabeled_as_safety_blocked() -> None:
    """数据库错误是 execution failed，旧 blocked_reason 不能泄露到公开安全字段。"""

    observation = _sql_observation(
        request=_request(), sql="SELECT 1", answer_hint="x",
        tool_result=SQLToolResult(
            safety_status="blocked", blocked_reason="driver error", error_type="sql_execution_error",
            tool_call=ToolCallTrace(tool_name="sql_query", status="error", error_type="sql_execution_error"),
        ),
        error_type="sql_execution_error", message="driver error",
    )

    assert (observation.execution_status, observation.safety_status, observation.answer_status) == ("failed", "passed", "no_answer")
    assert observation.blocked_reason is None
    assert observation.error_type == "sql_execution_error"


def test_known_semantic_request_rejection_keeps_m27_expected_rejection_semantics() -> None:
    """已知缺字段需求是确定性拒绝；这与模型/driver 技术失败必须分开。"""

    observation = _sql_observation(
        request=_request(), sql=None, answer_hint="x", tool_result=None,
        error_type="plan_validation_failed", message="请求了不存在的供应商字段",
        semantic_request_rejection=True,
    )

    assert (observation.execution_status, observation.answer_status, observation.safety_status) == (
        "completed", "unsupported", "blocked"
    )
    assert observation.reason_code == "semantic_request_validation"


def test_output_projection_rejection_is_a_deterministic_safety_contract() -> None:
    """候选 SQL 超出 QueryPlan 投影是执行前拒绝，不能被误归为 provider 不可用。"""

    observation = _sql_observation(
        request=_request(), sql="SELECT channel_name, region FROM channels", answer_hint="x", tool_result=None,
        error_type="output_projection_contract_failed", message="projection mismatch",
        output_projection_rejection=True,
    )

    assert (observation.execution_status, observation.answer_status, observation.safety_status) == (
        "completed", "no_answer", "blocked"
    )
    assert observation.blocked_reason is not None
    assert observation.error_type == "output_projection_contract_failed"


def test_sql_success_builds_stable_evidence_and_ledger() -> None:
    """只有成功 SQL 才产生可复算 fingerprint、EvidenceRef 和 generation-visible ledger。"""

    result = SQLToolResult(
        columns=["channel", "count"], rows=[{"channel": "Mobile App", "count": 3}], tables_used=["orders"],
        tool_call=ToolCallTrace(tool_name="sql_query", status="success"),
    )
    observation = _sql_observation(
        request=_request(), sql="SELECT channel, COUNT(*) AS count FROM orders", answer_hint="渠道订单量",
        tool_result=result, error_type=None, message=None,
    )

    assert (observation.execution_status, observation.answer_status, observation.safety_status) == ("completed", "complete", "passed")
    assert observation.evidence_refs[0]["evidence_kind"] == "sql"
    assert observation.ledger_projection is not None
    assert observation.ledger_projection["stages"][0]["stage"] == "generation_visible"
