"""M44 post-finish regression：用真实 SQL Tool 错误形状验证 dialect repair bridge。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import OperationalError

from engine.governance import demo_caller
from engine.harness.adapters import _sql_observation
from engine.harness.contracts import HarnessRequest
from engine.nl2sql.schema_loader import load_domain_schema
from engine.tools.sql_tool import run_sql_tool


class _MySQLError(Exception):
    """只模拟 DBAPI 的 `(error_number, message)` 形状，不依赖真实连接。"""


class _FailingSession:
    def __init__(self, error_number: int, raw_message: str) -> None:
        original = _MySQLError(error_number, raw_message)
        self._error = OperationalError("candidate sql", {}, original)

    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise self._error


def _request() -> HarnessRequest:
    return HarnessRequest(
        question="比较 2026 年 7 月和 8 月实际净退款金额。",
        run_id="m44-real-shape-regression",
        caller=demo_caller(caller_id="m44-real-shape", roles=("ops",)),
        active_sql_role="ops",
        force_new_pipeline=True,
    )


@pytest.mark.parametrize(
    ("error_number", "expected_reason", "expected_issue"),
    (
        (1305, "sql_dialect_incompatible", "mysql_unsupported_date_trunc"),
        (2006, "sql_execution_error", None),
    ),
)
def test_real_sql_tool_error_shape_drives_only_allowlisted_dialect_classification(
    error_number: int,
    expected_reason: str,
    expected_issue: str | None,
) -> None:
    """真实 Tool 的 `blocked` 结果仍可被 Harness 安全归类，但 generic error 不误修。"""

    raw_message = "RAW_DB_DRIVER_DETAIL_MUST_NOT_ESCAPE"
    sql = "SELECT DATE_TRUNC('month', refunds.processed_at) AS refund_month FROM refunds"
    result = run_sql_tool(
        db=_FailingSession(error_number, raw_message),  # type: ignore[arg-type]
        sql=sql,
        parameters={},
        user_role="ops",
        trace_id="m44-real-shape-regression",
        domain_schema=load_domain_schema(),
    )

    assert result.safety_status == "blocked"
    assert result.error_type == "sql_execution_error"
    assert result.issue_code == expected_issue
    assert raw_message not in json.dumps(
        {
            "blocked_reason": result.blocked_reason,
            "tool_call": result.tool_call.model_dump() if result.tool_call else None,
        },
        ensure_ascii=False,
    )

    observation = _sql_observation(
        request=_request(),
        sql=sql,
        answer_hint="Text2SQL 查询结果",
        tool_result=result,
        error_type=result.error_type,
        message=result.blocked_reason,
    )
    assert observation.safety_status == "passed"
    assert observation.reason_code == expected_reason
    assert observation.diagnostics.get("issue_code") == expected_issue
