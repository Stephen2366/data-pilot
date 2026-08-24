"""M44 PFIX-G4：两期指标比较的确定性完成合同。

这个模块只解决一个很窄的问题：SQL Evidence 已经安全取得两期同指标数值，但 SQL 本身
没有计算差额时，顶层 Agent 仍要完成用户明确要求的“比较”。它不解析自然语言、不生成
SQL，也不参与 dialect repair；可信输入只来自服务端 TaskState 约束与 typed requirement。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping

from engine.harness.contracts import ToolObservation
from engine.phase4b.identity import canonical_hash
from engine.phase4b.loop_contracts import EvidenceRequirement


ComparisonStatus = Literal["not_applicable", "complete", "blocked"]


@dataclass(frozen=True)
class ComparisonFact:
    """由两行已验证 SQL 结果派生的最小 typed 事实。"""

    baseline_period: str
    comparison_period: str
    metric: str
    baseline_value: Decimal
    comparison_value: Decimal
    absolute_difference: Decimal
    change_rate: Decimal

    @property
    def identity(self) -> str:
        return canonical_hash(self.safe_projection())

    def safe_projection(self) -> dict[str, str]:
        """只投影回答比较所需的数值，不携带任意 SQL rows。"""

        return {
            "baseline_period": self.baseline_period,
            "comparison_period": self.comparison_period,
            "metric": self.metric,
            "baseline_value": str(self.baseline_value),
            "comparison_value": str(self.comparison_value),
            "absolute_difference": str(self.absolute_difference),
            "change_rate": str(self.change_rate),
        }


@dataclass(frozen=True)
class ComparisonCompletion:
    """Controller 可消费的三态结果；blocked 必须带稳定 reason。"""

    status: ComparisonStatus
    reason_code: str
    observation: ToolObservation
    fact: ComparisonFact | None = None


def complete_metric_comparison(
    *,
    requirement: EvidenceRequirement,
    constraints: Mapping[str, Any],
    observation: ToolObservation,
) -> ComparisonCompletion:
    """验证两期结果、计算差额/变化率，并形成新的公开兼容 Observation。

    ★ requirement 与 constraints 都由服务端 Task runtime 产生。这里故意不读取 question，
    避免把“比较”“增长”等关键词变成隐藏控制协议。
    """

    periods = tuple(str(item) for item in constraints.get("periods", ()))
    if requirement.kind != "sql" or requirement.purpose != "metric_comparison" or len(periods) == 1:
        return ComparisonCompletion("not_applicable", "comparison_not_applicable", observation)
    if len(periods) != 2:
        return ComparisonCompletion("blocked", "comparison_period_count_unsupported", observation)

    metric = constraints.get("metric")
    if not isinstance(metric, str) or not metric.strip():
        return ComparisonCompletion("blocked", "comparison_metric_missing", observation)
    if observation.execution_status != "completed" or observation.safety_status != "passed":
        return ComparisonCompletion("blocked", "comparison_evidence_unavailable", observation)
    if len(observation.rows) != 2:
        return ComparisonCompletion("blocked", "comparison_row_count_mismatch", observation)

    period_column = _find_column(observation.columns, ("period", "month"))
    metric_column = _find_column(observation.columns, (metric,))
    if period_column is None or metric_column is None:
        return ComparisonCompletion("blocked", "comparison_projection_mismatch", observation)

    indexed: dict[str, tuple[dict[str, Any], Decimal]] = {}
    for raw_row in observation.rows:
        row = dict(raw_row)
        period = _normalize_period(row.get(period_column))
        value = _decimal(row.get(metric_column))
        if period is None or value is None:
            return ComparisonCompletion("blocked", "comparison_value_invalid", observation)
        if period in indexed:
            return ComparisonCompletion("blocked", "comparison_period_duplicate", observation)
        indexed[period] = (row, value)
    if set(indexed) != set(periods):
        return ComparisonCompletion("blocked", "comparison_period_mismatch", observation)

    baseline_row, baseline = indexed[periods[0]]
    comparison_row, comparison = indexed[periods[1]]
    if baseline == 0:
        return ComparisonCompletion("blocked", "comparison_baseline_zero", observation)

    difference = comparison - baseline
    rate = difference / baseline
    fact = ComparisonFact(periods[0], periods[1], metric, baseline, comparison, difference, rate)

    # 兼容旧 API 的二维 rows：按 TaskState 顺序重排，仅在比较期行追加稳定派生字段。
    # 原 SQL Evidence/ref/fingerprint 不改写；delta/rate 是 Agent completion 的派生事实。
    projected_rows = (baseline_row, {**comparison_row, "delta": float(difference), "rate": float(rate)})
    columns = tuple(dict.fromkeys((*observation.columns, "delta", "rate")))
    diagnostics = {
        **observation.diagnostics,
        "comparison_completion": {
            "status": "complete",
            "reason_code": "comparison_complete",
            "identity": fact.identity,
            **fact.safe_projection(),
        },
    }
    completed = replace(
        observation,
        answer=_answer(fact),
        columns=columns,
        rows=projected_rows,
        diagnostics=diagnostics,
    )
    return ComparisonCompletion("complete", "comparison_complete", completed, fact)


def _find_column(columns: tuple[str, ...], candidates: tuple[str, ...]) -> str | None:
    """closed-world、大小写不敏感地寻找稳定列名。"""

    lookup = {column.lower(): column for column in columns}
    return next((lookup[item.lower()] for item in candidates if item.lower() in lookup), None)


def _normalize_period(value: Any) -> str | None:
    """只接受 YYYY-MM 或可投影到 YYYY-MM 的 date/datetime/ISO 字符串。"""

    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m")
    text = str(value).strip() if value is not None else ""
    if len(text) >= 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit():
        month = int(text[5:7])
        return text[:7] if 1 <= month <= 12 else None
    return None


def _decimal(value: Any) -> Decimal | None:
    """拒绝 bool、NaN 与 Infinity，避免派生回答出现不可比较数值。"""

    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _display(value: Decimal) -> str:
    """将 Decimal 投影为无多余小数零的用户可读数字。"""

    normalized = format(value, "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _answer(fact: ComparisonFact) -> str:
    """从同一份 typed comparison fact 构造稳定中文回答。"""

    direction = "增加" if fact.absolute_difference >= 0 else "减少"
    difference = abs(fact.absolute_difference)
    percentage = abs(fact.change_rate * Decimal("100"))
    return (
        f"{fact.baseline_period} 的实际净退款金额为 {_display(fact.baseline_value)}，"
        f"{fact.comparison_period} 为 {_display(fact.comparison_value)}；"
        f"{fact.comparison_period} 比 {fact.baseline_period} {direction} {_display(difference)}，"
        f"变化率为 {_display(percentage)}%。"
    )
