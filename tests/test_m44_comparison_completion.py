"""PFIX-G4：typed 两期比较完成器的纯合同与失败关闭测试。"""

from __future__ import annotations

from engine.harness.contracts import ToolObservation
from engine.phase4b.comparison_completion import complete_metric_comparison
from engine.phase4b.loop_contracts import EvidenceRequirement


def _requirement() -> EvidenceRequirement:
    return EvidenceRequirement(
        "sql:net_refund_amount:2026-07,2026-08",
        "sql",
        "metric_comparison",
        "受控查询文本",
    )


def _observation(rows: tuple[dict[str, object], ...]) -> ToolObservation:
    return ToolObservation(
        tool_name="text2sql",
        route="sql",
        execution_status="completed",
        answer_status="complete",
        safety_status="passed",
        reason_code="sql_completed",
        answer="仅返回原始两行。",
        columns=("month", "net_refund_amount"),
        rows=rows,
        evidence_refs=({"evidence_id": "safe-sql-evidence"},),
    )


def _constraints(*periods: str) -> dict[str, object]:
    return {"metric": "net_refund_amount", "periods": periods, "comparison": len(periods) > 1}


def test_two_period_rows_are_ordered_and_completed_without_query_keywords() -> None:
    result = complete_metric_comparison(
        requirement=_requirement(),
        constraints=_constraints("2026-07", "2026-08"),
        observation=_observation((
            {"month": "2026-08-01", "net_refund_amount": 180000.0},
            {"month": "2026-07-01", "net_refund_amount": 120000.0},
        )),
    )

    assert result.status == "complete" and result.fact is not None
    assert result.fact.absolute_difference == 60000
    assert result.fact.change_rate == 0.5
    assert result.observation.rows[0]["month"] == "2026-07-01"
    assert result.observation.rows[1]["delta"] == 60000.0
    assert result.observation.rows[1]["rate"] == 0.5
    assert "增加 60000" in (result.observation.answer or "")
    assert "comparison_completion" in result.observation.diagnostics


def test_single_period_is_not_applicable_and_does_not_rewrite_observation() -> None:
    observation = _observation(({"month": "2026-07-01", "net_refund_amount": 120000},))
    result = complete_metric_comparison(
        requirement=_requirement(), constraints=_constraints("2026-07"), observation=observation,
    )
    assert result.status == "not_applicable" and result.observation is observation


def test_invalid_shape_value_period_and_zero_baseline_fail_closed() -> None:
    cases = (
        (
            ({"month": "2026-07-01", "net_refund_amount": 120000},),
            "comparison_row_count_mismatch",
        ),
        (
            (
                {"month": "2026-07-01", "net_refund_amount": "not-a-number"},
                {"month": "2026-08-01", "net_refund_amount": 180000},
            ),
            "comparison_value_invalid",
        ),
        (
            (
                {"month": "2026-07-01", "net_refund_amount": 120000},
                {"month": "2026-09-01", "net_refund_amount": 180000},
            ),
            "comparison_period_mismatch",
        ),
        (
            (
                {"month": "2026-07-01", "net_refund_amount": 0},
                {"month": "2026-08-01", "net_refund_amount": 10},
            ),
            "comparison_baseline_zero",
        ),
    )
    for rows, reason in cases:
        result = complete_metric_comparison(
            requirement=_requirement(),
            constraints=_constraints("2026-07", "2026-08"),
            observation=_observation(rows),
        )
        assert result.status == "blocked" and result.reason_code == reason
        assert result.observation.rows == rows
