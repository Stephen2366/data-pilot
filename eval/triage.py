"""M19 Failure Triage：把 eval 的 pass/fail 变成可行动的失败归因。

LangFuse 已经能记录 trace 和 score 后，下一步价值不是“多一个网页”，而是让失败 case 能被
稳定聚合：到底该修 schema retrieval、QueryPlan、SQL 生成、安全策略、SQL 执行，还是 scorer。

★ 本模块坚持本地优先：输入只依赖 `EvalResult` 和 JSONL trace。LangFuse payload 是可选输出，
Cloud 不可用时 Markdown / JSON triage 仍完整生成。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from eval.scorers.base import LangFuseScorePayload

FailureStage = Literal[
    "schema_retrieval",
    "schema_context",
    "query_plan",
    "plan_validation",
    "sql_generation",
    "sql_guard",
    "sql_execution",
    "output_contract",
    "result_match",
    "answer_synthesis",
    "scorer_issue",
    "judge_unavailable",
    "unknown",
]

# ★ M24 新增独立 `output_contract` 大阶段；subtype 继续细分“Schema 真缺失”和
# “最终 SQL 输出契约不匹配”，避免把 scorer 的列名检查误读成 embedding 失败。
FailureSubtype = Literal[
    "output_table_contract",
    "output_column_contract",
    "result_contract",
    "scorer_contract",
]

NeedsAction = Literal[
    "fix_pipeline",
    "fix_schema_desc",
    "fix_scorer",
    "fix_case",
    "manual_review",
    "infra_retry",
]

TRACE_STAGE_BY_STEP_TYPE: dict[str, FailureStage] = {
    "schema_retrieval": "schema_retrieval",
    "schema_context": "schema_context",
    "join_path": "query_plan",
    "query_plan": "query_plan",
    "plan_validation": "plan_validation",
    "sql_generation": "sql_generation",
    "sql_guard": "sql_guard",
    "sql_execution": "sql_execution",
    "output_contract": "output_contract",
}

STAGE_BY_ERROR_TYPE: dict[str, FailureStage] = {
    "insufficient_schema_context": "schema_retrieval",
    "invalid_query_plan": "query_plan",
    "unsupported_multi_step_plan": "query_plan",
    "plan_validation_failed": "plan_validation",
    "missing_column": "plan_validation",
    "invalid_join_path": "plan_validation",
    "unsupported_relation": "plan_validation",
    "sensitive_field_access": "sql_guard",
    "sql_guard_blocked": "sql_guard",
    "sql_execution_error": "sql_execution",
    "llm_generation_error": "sql_generation",
    "sql_plan_contract_failed": "sql_generation",
    "sql_plan_contract_indeterminate": "sql_generation",
    "output_projection_contract_failed": "output_contract",
}


@dataclass(frozen=True)
class FailureTriage:
    """单条 case 的 M19 归因结果。

    `failed` 为 False 时仍可写 `triage:failed=0` 到 LangFuse，方便 UI 里筛选“全部 case 中哪些失败”。
    `failure_stage` 只在失败、跳过或人工复核时代表排障建议；通过 case 固定为 `unknown`。
    """

    case_id: str
    question: str
    failed: bool
    failure_stage: FailureStage
    failure_reason: str
    needs_action: NeedsAction
    evidence_step: str
    confidence: float
    failure_subtype: FailureSubtype | None = None
    trace_id: str | None = None
    langfuse_trace_id: str | None = None
    langfuse_write_status: str = "skipped"
    regression_candidate: bool = False


def load_trace_records(trace_path: Path) -> dict[str, dict[str, Any]]:
    """读取 JSONL trace，按 DataPilot trace_id 建立索引。

    这里容忍坏行和缺字段，因为 eval 主报告不能被一个损坏 trace 阻断；证据不足时 triage 会落到
    `unknown/manual_review`。
    """

    if not trace_path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        trace_id = record.get("trace_id")
        if trace_id:
            records[str(trace_id)] = record
    return records


def triage_results(results: list[Any], *, trace_path: Path) -> list[FailureTriage]:
    """为一批 EvalResult 生成 triage；通过 case 也保留一条轻量记录。"""

    trace_records = load_trace_records(trace_path)
    return [triage_result(result, trace_records.get(result.trace_id or "")) for result in results]


def triage_result(result: Any, trace_record: dict[str, Any] | None = None) -> FailureTriage:
    """归因单条 EvalResult。

    规则顺序刻意和 pipeline 执行顺序、scorer 早返回顺序一致：越靠前的硬失败越优先，最后才看
    输出匹配和 scorer/judge 问题。
    """

    trace_record = trace_record or {}
    failed = bool(
        (not result.passed)
        or result.skipped_due_to_pipeline_mode
        or result.review_required
        or result.status_code >= 400
    )
    langfuse_trace_id = trace_record.get("langfuse_trace_id")
    langfuse_write_status = str(trace_record.get("langfuse_write_status") or "skipped")

    # 步骤 1：通过 case 也保留轻量 triage，服务 LangFuse `triage:failed=0` 筛选 ==========
    if not failed:
        return FailureTriage(
            case_id=result.case.case_id,
            question=result.case.question,
            failed=False,
            failure_stage="unknown",
            failure_reason="case_passed",
            needs_action="manual_review",
            evidence_step="-",
            confidence=0.0,
            trace_id=result.trace_id,
            langfuse_trace_id=langfuse_trace_id,
            langfuse_write_status=langfuse_write_status,
            regression_candidate=False,
        )

    # 步骤 2：优先相信 trace step 的失败边界；它最接近真实 pipeline 执行位置 ----------
    failed_step = _first_failed_trace_step(trace_record)
    if failed_step is not None:
        stage = TRACE_STAGE_BY_STEP_TYPE.get(str(failed_step.get("step_type") or failed_step.get("name")), "unknown")
        error_type = str(failed_step.get("error_type") or "")
        subtype: FailureSubtype | None = (
            "output_column_contract" if error_type == "output_projection_contract_failed" else None
        )
        return _triage(
            result,
            trace_record,
            stage=stage,
            subtype=subtype,
            reason=f"trace_step_status={failed_step.get('status')} error_type={failed_step.get('error_type')}",
            evidence=f"trace:{failed_step.get('name') or failed_step.get('step_type')}",
            confidence=1.0,
        )

    # 步骤 3：没有失败 step 时，再用响应层 error_type 做阶段归因 -----------------------
    error_type = result.error_type or trace_record.get("error_type")
    if error_type:
        stage = STAGE_BY_ERROR_TYPE.get(str(error_type), "unknown")
        return _triage(
            result,
            trace_record,
            stage=stage,
            reason=f"error_type={error_type}",
            evidence=f"error_type:{error_type}",
            confidence=0.9 if stage != "unknown" else 0.5,
        )

    # 步骤 4：最后回到 scorer 明细；它能解释“SQL 跑通但评分没过”的情况 ---------------
    failed_detail = _first_failed_score_detail(result)
    if failed_detail is not None:
        stage = _stage_from_score_detail(failed_detail, result)
        subtype = _subtype_from_score_detail(failed_detail)
        return _triage(
            result,
            trace_record,
            stage=stage,
            subtype=subtype,
            reason=failed_detail.reason or f"score_failed={failed_detail.name}",
            evidence=f"score:{failed_detail.name}",
            confidence=0.8 if stage != "unknown" else 0.5,
            needs_action=(
                "manual_review"
                if result.review_required and subtype in {"output_table_contract", "output_column_contract"}
                else None
            ),
        )

    if result.skipped_due_to_pipeline_mode:
        return _triage(
            result,
            trace_record,
            stage="scorer_issue",
            reason="case requires a pipeline mode that this run did not execute",
            evidence="score:rule:pipeline_mode_supported",
            confidence=1.0,
            needs_action="manual_review",
            regression_candidate=False,
        )

    if result.review_required:
        return _triage(
            result,
            trace_record,
            stage="unknown",
            reason="manual_review_required",
            evidence="score:manual_review",
            confidence=0.0,
            needs_action="manual_review",
            regression_candidate=False,
        )

    return _triage(
        result,
        trace_record,
        stage="unknown",
        reason=result.reason or "insufficient evidence for triage",
        evidence="result:summary",
        confidence=0.0,
        needs_action="manual_review",
    )


def build_triage_score_payloads(triages: list[FailureTriage]) -> list[LangFuseScorePayload]:
    """把 triage 结果转成 LangFuse score payloads。

    只有 JSONL 明确记录 `langfuse_write_status=ok` 的 trace 才回写，避免往未确认或失败 trace 上写
    score。categorical/text score 的支持由 LangFuse SDK 负责；本地报告不依赖它。
    """

    payloads: list[LangFuseScorePayload] = []
    for triage in triages:
        if not triage.langfuse_trace_id or triage.langfuse_write_status != "ok":
            continue
        common_metadata = {
            "case_id": triage.case_id,
            "datapilot_trace_id": triage.trace_id,
            "failure_reason": triage.failure_reason,
            "evidence_step": triage.evidence_step,
            "regression_candidate": triage.regression_candidate,
        }
        payloads.extend(
            [
                LangFuseScorePayload(
                    trace_id=triage.langfuse_trace_id,
                    name="triage:failed",
                    value=1.0 if triage.failed else 0.0,
                    data_type="NUMERIC",
                    comment=triage.failure_reason,
                    metadata=common_metadata,
                ),
                LangFuseScorePayload(
                    trace_id=triage.langfuse_trace_id,
                    name="triage:failure_stage",
                    value=triage.failure_stage,
                    data_type="CATEGORICAL",
                    comment=triage.failure_reason,
                    metadata=common_metadata,
                ),
                LangFuseScorePayload(
                    trace_id=triage.langfuse_trace_id,
                    name="triage:needs_action",
                    value=triage.needs_action,
                    data_type="CATEGORICAL",
                    comment=triage.failure_reason,
                    metadata=common_metadata,
                ),
                LangFuseScorePayload(
                    trace_id=triage.langfuse_trace_id,
                    name="triage:confidence",
                    value=triage.confidence,
                    data_type="NUMERIC",
                    comment=triage.failure_reason,
                    metadata=common_metadata,
                ),
            ]
        )
    return payloads


def triage_summary(triages: list[FailureTriage]) -> dict[str, Any]:
    """生成 Markdown 和 JSON 共用的聚合摘要。"""

    failed_triages = [triage for triage in triages if triage.failed]
    return {
        "total": len(triages),
        "failed": len(failed_triages),
        "failure_stage_counts": dict(Counter(triage.failure_stage for triage in failed_triages)),
        "failure_subtype_counts": dict(
            Counter(triage.failure_subtype for triage in failed_triages if triage.failure_subtype)
        ),
        "needs_action_counts": dict(Counter(triage.needs_action for triage in failed_triages)),
        "top_cases": [asdict(triage) for triage in _top_triage_cases(failed_triages)],
        "regression_candidates": [asdict(triage) for triage in failed_triages if triage.regression_candidate],
    }


def write_triage_json(triages: list[FailureTriage], path: Path) -> None:
    """输出本地 triage JSON，供 A/B failure distribution 对比使用。"""

    payload = {
        "summary": triage_summary(triages),
        "cases": [asdict(triage) for triage in triages],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def compare_triage_files(*, left_path: Path, right_path: Path, output_path: Path) -> None:
    """比较两个 triage JSON 的失败阶段分布，并输出 Markdown。

    M19 只做本地对比，不自动创建 LangFuse Dataset / Experiment。
    """

    left = _load_triage_json(left_path)
    right = _load_triage_json(right_path)
    left_counts = Counter(left.get("summary", {}).get("failure_stage_counts") or {})
    right_counts = Counter(right.get("summary", {}).get("failure_stage_counts") or {})
    stages = sorted(set(left_counts) | set(right_counts))

    lines = [
        "# M19 A/B Failure Distribution",
        "",
        f"- left: {left_path}",
        f"- right: {right_path}",
        "",
        "| failure_stage | left | right | delta_right_minus_left |",
        "|---|---:|---:|---:|",
    ]
    for stage in stages:
        left_value = int(left_counts.get(stage, 0))
        right_value = int(right_counts.get(stage, 0))
        lines.append(f"| {stage} | {left_value} | {right_value} | {right_value - left_value} |")

    left_subtypes = Counter(left.get("summary", {}).get("failure_subtype_counts") or {})
    right_subtypes = Counter(right.get("summary", {}).get("failure_subtype_counts") or {})
    subtypes = sorted(set(left_subtypes) | set(right_subtypes))
    if subtypes:
        lines.extend(
            [
                "",
                "## Failure Subtype Distribution",
                "",
                "| failure_subtype | left | right | delta_right_minus_left |",
                "|---|---:|---:|---:|",
            ]
        )
        for subtype in subtypes:
            left_value = int(left_subtypes.get(subtype, 0))
            right_value = int(right_subtypes.get(subtype, 0))
            lines.append(f"| {subtype} | {left_value} | {right_value} | {right_value - left_value} |")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _triage(
    result: Any,
    trace_record: dict[str, Any],
    *,
    stage: FailureStage,
    subtype: FailureSubtype | None = None,
    reason: str,
    evidence: str,
    confidence: float,
    needs_action: NeedsAction | None = None,
    regression_candidate: bool | None = None,
) -> FailureTriage:
    """集中补全 action / candidate 等派生字段。"""

    resolved_action = needs_action or _needs_action(stage, result)
    resolved_candidate = (
        regression_candidate
        if regression_candidate is not None
        else stage not in {"scorer_issue", "judge_unavailable", "unknown"} and not result.review_required
    )
    return FailureTriage(
        case_id=result.case.case_id,
        question=result.case.question,
        failed=True,
        failure_stage=stage,
        failure_subtype=subtype,
        failure_reason=reason,
        needs_action=resolved_action,
        evidence_step=evidence,
        confidence=confidence,
        trace_id=result.trace_id,
        langfuse_trace_id=trace_record.get("langfuse_trace_id"),
        langfuse_write_status=str(trace_record.get("langfuse_write_status") or "skipped"),
        regression_candidate=resolved_candidate,
    )


def _first_failed_trace_step(trace_record: dict[str, Any]) -> dict[str, Any] | None:
    """找出 trace 里最早的非成功步骤。"""

    for step in trace_record.get("trace_steps") or []:
        status = str(step.get("status") or "")
        if status in {"error", "blocked", "failed"} or step.get("error_type"):
            return step
    return None


def _first_failed_score_detail(result: Any) -> Any | None:
    """找出 scorer 明细里第一条失败项。"""

    for detail in result.score_details:
        if detail.passed is False and not detail.skipped:
            return detail
    return None


def _stage_from_score_detail(detail: Any, result: Any) -> FailureStage:
    """把 scorer 名称和 issue tag 映射到失败阶段。"""

    if detail.name == "rule:table_hit":
        return "output_contract"
    if detail.name == "rule:column_recall":
        return "output_contract"
    if detail.name == "rule:safety_compliance":
        return "sql_guard"
    if detail.name == "rule:sql_success":
        return "sql_execution" if result.error_type == "sql_execution_error" else "unknown"
    if "output_projection_mismatch" in detail.issue_tags:
        return "output_contract"
    if detail.name in {"rule:result_match", "rule:expected_value", "rule:contains", "rule:equals"}:
        return "result_match"
    if detail.name == "llm:correctness":
        if detail.skipped or "judge" in detail.reason.lower():
            return "judge_unavailable"
        return "answer_synthesis"
    if "result_mismatch" in detail.issue_tags:
        return "result_match"
    if "missing_table" in detail.issue_tags:
        return "output_contract"
    if "missing_column" in detail.issue_tags:
        return "output_contract"
    if "safety_mismatch" in detail.issue_tags:
        return "sql_guard"
    return "scorer_issue" if result.review_required else "unknown"


def _subtype_from_score_detail(detail: Any) -> FailureSubtype | None:
    """给 scorer 失败补充细分类，不改变既有 failure_stage 的兼容口径。

    `rule:table_hit` / `rule:column_recall` 比较的是最终响应里的 `tables_used` / `columns`，
    并不能单独证明 SchemaGraph 或 embedding 缺失。因此把它们标成 output contract，后续
    必须先核对 SQL 生成和 case alias，再决定是否修 Schema Retrieval。
    """

    issue_tags = detail.issue_tags or []
    if "output_projection_mismatch" in issue_tags:
        return "output_column_contract"
    if detail.name == "rule:table_hit" or "missing_table" in issue_tags:
        return "output_table_contract"
    if detail.name == "rule:column_recall" or "missing_column" in issue_tags:
        return "output_column_contract"
    if detail.name in {"rule:result_match", "rule:expected_value", "rule:contains", "rule:equals"}:
        return "result_contract"
    if str(detail.name).startswith("rule:"):
        return "scorer_contract"
    return None


def _needs_action(stage: FailureStage, result: Any) -> NeedsAction:
    """按 failure_stage 给默认下一步动作。"""

    if result.review_required or stage == "unknown":
        return "manual_review"
    if stage in {"schema_retrieval", "schema_context"}:
        return "fix_schema_desc"
    if stage in {"scorer_issue"}:
        return "fix_scorer"
    if stage == "judge_unavailable":
        return "infra_retry"
    if stage in {
        "query_plan",
        "plan_validation",
        "sql_generation",
        "sql_guard",
        "sql_execution",
        "output_contract",
        "result_match",
        "answer_synthesis",
    }:
        return "fix_pipeline"
    return "manual_review"


def _top_triage_cases(triages: list[FailureTriage], *, limit: int = 10) -> list[FailureTriage]:
    """挑出报告里最值得优先看的失败 case。"""

    priority = {
        "sql_guard": 0,
        "sql_execution": 1,
        "output_contract": 2,
        "schema_retrieval": 3,
        "schema_context": 4,
        "query_plan": 5,
        "plan_validation": 6,
        "sql_generation": 7,
        "result_match": 8,
        "answer_synthesis": 9,
        "scorer_issue": 10,
        "judge_unavailable": 11,
        "unknown": 12,
    }
    return sorted(triages, key=lambda item: (priority[item.failure_stage], -item.confidence, item.case_id))[:limit]


def _load_triage_json(path: Path) -> dict[str, Any]:
    """读取 triage JSON；错误让调用方直接看到，避免 A/B 报告悄悄用空数据。"""

    return json.loads(path.read_text(encoding="utf-8"))
