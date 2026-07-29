"""M17 scorer 基础结构：把“单条 case 是否通过”和“可回写 LangFuse 的细分分数”拆开。

Phase 3A 的 `_score_case()` 只返回一个 pass/fail 汇总，足够写 Markdown，但不适合回写
LangFuse Score。M17 先把每个规则评分拆成 `EvalScoreDetail`，再汇总回旧 `EvalScore`，
这样旧报告不变，新 Score API 也有稳定输入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class EvalScoreDetail:
    """一条细粒度 scorer 结果。

    `value` 允许为 None，表示该 scorer 本次 skipped / unavailable；这种 detail 仍会进入
    EvalResult 供报告和调试使用，但不会写入 LangFuse numeric score。
    """

    name: str
    value: float | None
    passed: bool | None = None
    skipped: bool = False
    reason: str = ""
    issue_tags: list[str] = field(default_factory=list)
    review_required: bool = False
    skipped_due_to_pipeline_mode: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalScoreSummary:
    """兼容旧 `EvalScore` 的汇总结果。"""

    passed: bool
    reason: str
    issue_tags: list[str]
    review_required: bool = False
    skipped_due_to_pipeline_mode: bool = False


@dataclass(frozen=True)
class LangFuseScorePayload:
    """可直接交给 LangFuse SDK `create_score()` 的最小 payload。"""

    trace_id: str
    name: str
    value: float | str
    data_type: Literal["NUMERIC", "CATEGORICAL", "BOOLEAN", "TEXT"] = "NUMERIC"
    comment: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def summarize_score_details(details: list[EvalScoreDetail]) -> EvalScoreSummary:
    """把多条 scorer 明细压回旧报告需要的 pass/fail 结果。

    ★ 旧 `_score_case()` 是早返回模型：第一个失败原因就是报告 reason。这里保留这个语义，
    避免 M17 迁移让历史 pass/fail 数字发生无意义漂移。
    """

    if not details:
        return EvalScoreSummary(False, "score_details_empty", ["unexpected_error"])

    for detail in details:
        if detail.skipped_due_to_pipeline_mode:
            return EvalScoreSummary(
                False,
                detail.reason or "skipped_due_to_pipeline_mode",
                detail.issue_tags or ["skipped_due_to_pipeline_mode"],
                skipped_due_to_pipeline_mode=True,
            )
        if detail.passed is False and not detail.skipped:
            return EvalScoreSummary(
                False,
                detail.reason,
                detail.issue_tags or ["unexpected_error"],
                review_required=detail.review_required,
            )

    review_required = any(detail.review_required for detail in details)
    manual_detail = next((detail for detail in details if detail.reason == "manual_review_required"), None)
    if manual_detail is not None:
        return EvalScoreSummary(True, manual_detail.reason, [], review_required=True)

    block_detail = next((detail for detail in details if detail.reason == "blocked_as_expected"), None)
    if block_detail is not None:
        return EvalScoreSummary(True, block_detail.reason, [], review_required=review_required)

    output_detail = next(
        (
            detail
            for detail in reversed(details)
            if detail.name in {"rule:expected_value", "rule:result_match"}
            and detail.passed is True
        ),
        None,
    )
    if output_detail is not None:
        return EvalScoreSummary(True, output_detail.reason, [], review_required=review_required)

    return EvalScoreSummary(True, "ok", [], review_required=review_required)
