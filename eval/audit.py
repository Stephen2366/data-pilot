"""M26 人工审计证据层：把冻结的一轮 eval 输入组装成可复查的逐题审计卷。

这里像法院的“卷宗整理员”：只把 case 合同、已有 trace、自动评分与 triage 放到同一份
记录中，不重新调用 LLM、不修改正式评分，也不让 Markdown 反向成为第二份事实源。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from eval.run_eval import EvalCase


AuditVerdict = Literal["pass", "fail", "unavailable", "insufficient_evidence"]
Reconciliation = Literal["agree", "false_positive", "false_negative", "status_mismatch", "unresolved"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class FrozenInput:
    """一份审计输入的路径和 hash，防止事后把别轮 run 混进同一个审计包。"""

    label: str
    path: str
    sha256: str
    byte_count: int


@dataclass(frozen=True)
class AuditRunManifest:
    """冻结 run 的身份信息；长期产物只保存相对项目根路径，跨机器仍可阅读。"""

    audit_schema_version: str
    run_id: str
    case_contract_version: str
    case_count: int
    generated_at_utc: str
    inputs: list[FrozenInput]
    runtime_metadata: dict[str, Any]


def _file_fingerprint(path: Path, *, project_root: Path) -> FrozenInput:
    """读取一次冻结输入并计算内容 hash；不存在时明确失败，不猜测其它轮次路径。"""

    if not path.is_file():
        raise ValueError(f"audit input missing: {path}")
    content = path.read_bytes()
    try:
        display_path = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        display_path = str(path)
    return FrozenInput(
        label=path.suffix.lstrip(".") or "file",
        path=display_path,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
    )


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    """加载结构化输入；坏 JSON 不能静默退化成空证据。"""

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"audit {label} is not valid JSON: {path}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"audit {label} must be a JSON object: {path}")
    return loaded


def _load_trace_records(path: Path) -> dict[str, dict[str, Any]]:
    """按 trace_id 索引 JSONL；缺 ID 或坏行是证据缺失，不能被默默跳过。"""

    if not path.is_file():
        raise ValueError(f"audit trace missing: {path}")
    records: dict[str, dict[str, Any]] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"audit trace has invalid JSON at line {line_number}: {path}") from exc
        trace_id = str(record.get("trace_id") or "")
        if not trace_id:
            raise ValueError(f"audit trace lacks trace_id at line {line_number}: {path}")
        if trace_id in records:
            raise ValueError(f"audit trace_id duplicated: {trace_id}")
        records[trace_id] = record
    return records


def _parse_markdown_bool(value: str) -> bool | None:
    """解析历史 report 里的三态 passed 列；`None` 是健康指标而非通过或失败。"""

    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _load_legacy_report_scores(path: Path) -> dict[str, list[dict[str, Any]]]:
    """读取既有 run 唯一留下的 score 明细。

    M25 的历史 runner 尚未把 ``EvalResult.score_details`` 单独落成 JSON；P0 不能为了补齐
    这部分证据重跑 scorer（`result_match` 会执行 SQLite SQL）。因此此处是有界的历史迁移
    adapter：只读取已冻结 report 的 ``Score Summary``，并在 record 标记该来源。新审计记录
    本身仍以 JSON 为唯一结构化事实源，Markdown 不会反向参与后续人工 verdict 或汇总。
    """

    if not path.is_file():
        raise ValueError(f"audit report missing: {path}")
    in_scores = False
    scores: dict[str, list[dict[str, Any]]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line == "## Score Summary":
            in_scores = True
            continue
        if in_scores and raw_line.startswith("## "):
            break
        if not in_scores or not raw_line.startswith("| ") or raw_line.startswith("| case_id "):
            continue
        cells = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        if len(cells) != 6 or cells[0] == "---":
            continue
        case_id, name, value, passed, skipped, reason = cells
        scores.setdefault(case_id, []).append(
            {"name": name, "value": value, "passed": _parse_markdown_bool(passed), "skipped": _parse_markdown_bool(skipped) is True, "reason": reason}
        )
    if not scores:
        raise ValueError(f"audit report has no parseable Score Summary: {path}")
    return scores


def _automated_summary(score_details: list[dict[str, Any]]) -> tuple[bool, bool, str]:
    """从冻结的历史 score table 重建 runner pass/review；不运行任何 scorer 或 SQL。"""

    failed = [detail for detail in score_details if detail["passed"] is False and not detail["skipped"]]
    review_required = any(detail["name"] == "rule:manual_review" for detail in score_details)
    return not failed, review_required, failed[0]["reason"] if failed else "manual_review_required" if review_required else "all_score_details_passed"


def _find_step(trace: dict[str, Any], step_type: str) -> dict[str, Any] | None:
    """从单条冻结 trace 取指定阶段；未出现时返回 None，让 record 明确保留证据缺口。"""

    return next((step for step in trace.get("trace_steps") or [] if step.get("step_type") == step_type), None)


def _redact_result_rows(rows: Any, *, limit: int = 5) -> list[dict[str, Any]]:
    """只保留审计所需的少量执行结果，并遵守敏感字段公开边界。"""

    protected_suffixes = ("email", "phone")
    safe_rows: list[dict[str, Any]] = []
    for row in list(rows or [])[:limit]:
        if not isinstance(row, dict):
            continue
        safe_rows.append(
            {
                str(key): "[redacted]" if str(key).lower().endswith(protected_suffixes) else value
                for key, value in row.items()
            }
        )
    return safe_rows


def _sql_state(trace: dict[str, Any], response: dict[str, Any]) -> tuple[str, str | None]:
    """区分没有生成 SQL、已被 Guard 拦截、执行失败和正常完成，避免把空 SQL 当语义错误。"""

    sql = response.get("sql")
    guard_step = _find_step(trace, "sql_guard")
    execution_step = _find_step(trace, "sql_query")
    if sql:
        if guard_step and guard_step.get("status") == "blocked":
            return "blocked", str(sql)
        if execution_step and execution_step.get("status") in {"error", "failed"}:
            return "execution_failed", str(sql)
        return "executed", str(sql)
    if guard_step and guard_step.get("status") == "blocked":
        return "blocked_without_sql", None
    return "unavailable", None


def _contract(case: EvalCase) -> dict[str, Any]:
    """从唯一的 EvalCase 构造审计视图，不复制或解析 YAML 文本。"""

    return {
        "question": case.question,
        "check_type": case.check_type,
        "check": case.check,
        "expected_tables": case.expected_tables,
        "expected_tables_alternatives": case.expected_tables_alternatives,
        "expected_columns": case.expected_columns,
        "expected_metrics": case.expected_metrics,
        "expected_plan": case.expected_plan,
        "expected_schema_context": case.expected_schema_context,
        "expected_sql": case.expected_sql,
        "contract_adjustment": case.contract_adjustment,
        "source_file": case.source_file,
    }


def build_audit_records(
    *,
    cases: list[EvalCase],
    trace_path: Path,
    report_path: Path,
    triage_path: Path,
    project_root: Path,
    run_id: str,
    case_contract_version: str,
    runtime_metadata: dict[str, Any],
) -> tuple[AuditRunManifest, list[dict[str, Any]]]:
    """组装一轮不可变的 audit records；不调用 LLM、DB 或 SQL Guard。

    triage JSON 的 case_id -> trace_id 是历史 JSONL 将同题 linked case 唯一对应到 trace 的桥梁。
    缺少任一 case、trace 或 triage 身份时立即失败，绝不从其它 run 自动补全。
    """

    trace_records = _load_trace_records(trace_path)
    triage_payload = _load_json(triage_path, label="triage")
    report_scores = _load_legacy_report_scores(report_path)
    triage_cases = triage_payload.get("cases")
    if not isinstance(triage_cases, list):
        raise ValueError(f"audit triage lacks cases list: {triage_path}")
    triage_by_case = {str(item.get("case_id") or ""): item for item in triage_cases if isinstance(item, dict)}
    expected_ids = [case.case_id for case in cases]
    if len(triage_by_case) != len(expected_ids) or set(triage_by_case) != set(expected_ids):
        raise ValueError("audit case/triage identity mismatch; refusing to combine different runs")

    manifest = AuditRunManifest(
        audit_schema_version="m26-v1",
        run_id=run_id,
        case_contract_version=case_contract_version,
        case_count=len(cases),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        inputs=[
            _file_fingerprint(trace_path, project_root=project_root),
            _file_fingerprint(report_path, project_root=project_root),
            _file_fingerprint(triage_path, project_root=project_root),
        ],
        runtime_metadata=runtime_metadata,
    )

    records: list[dict[str, Any]] = []
    for position, case in enumerate(cases, start=1):
        triage = triage_by_case[case.case_id]
        trace_id = str(triage.get("trace_id") or "")
        trace = trace_records.get(trace_id)
        if trace is None:
            raise ValueError(f"audit trace missing for case={case.case_id} trace_id={trace_id or '<empty>'}")
        if trace.get("question") != case.question:
            raise ValueError(f"audit question mismatch for case={case.case_id}; refusing positional fallback")
        score_details = report_scores.get(case.case_id)
        if not score_details:
            raise ValueError(f"audit report lacks score details for case={case.case_id}")

        response = {key: value for key, value in trace.items() if key not in {"trace_steps", "tool_calls"}}
        trace_steps = list(trace.get("trace_steps") or [])
        runner_passed, review_required, runner_reason = _automated_summary(score_details)
        context_step = _find_step(trace, "schema_context") or {}
        retrieval_step = _find_step(trace, "schema_retrieval") or {}
        plan_step = _find_step(trace, "query_plan") or {}
        sql_step = _find_step(trace, "sql_generation") or {}
        sql_state, sql = _sql_state(trace, response)
        records.append(
            {
                "record_id": f"{run_id}:{case.case_id}",
                "position": position,
                "identity": {
                    "run_id": run_id,
                    "case_id": case.case_id,
                    "semantic_group_id": case.semantic_group_id,
                    "linked_case_id": case.linked_case_id,
                    "case_contract_version": case_contract_version,
                    "trace_id": trace_id,
                    "source_case": case.source_file,
                    "runtime": runtime_metadata,
                },
                "question_contract": _contract(case),
                "pipeline_evidence": {
                    "retrieval": retrieval_step.get("metadata") or {},
                    "schema_context": context_step.get("metadata") or {},
                    "query_plan": plan_step,
                    "plan_validation": _find_step(trace, "plan_validation"),
                    "sql_generation": sql_step,
                    "sql_state": sql_state,
                    "candidate_sql": sql,
                    "sql_guard": _find_step(trace, "sql_guard"),
                    "execution": _find_step(trace, "sql_query"),
                    "transport_failure_steps": [
                        step for step in trace_steps if step.get("status") in {"error", "blocked", "failed"}
                    ],
                },
                "result_evidence": {
                    "columns": response.get("columns") or [],
                    "row_count": len(response.get("rows") or []),
                    "row_sample": _redact_result_rows(response.get("rows")),
                    "reference_sql": case.expected_sql or None,
                    "automatic_score_details": score_details,
                    "automatic_score_evidence": "legacy_frozen_report_score_summary; report_hash_frozen; no_scorer_or_sql_replay",
                },
                "automated_verdict": {
                    "runner_passed_reconstructed": runner_passed,
                    "review_required_reconstructed": review_required,
                    "reason_reconstructed": runner_reason,
                    "triage": triage,
                },
                # P0 只建立固定槽位；P1 的独立审计结论由 apply_audit_verdicts 写入副本。
                "audit_verdict": None,
                "reconciliation": None,
            }
        )
    return manifest, records


def _reconciliation(*, automated_passed: bool, audit_verdict: AuditVerdict) -> Reconciliation:
    """把人工 verdict 与自动判定转为固定枚举，避免报告只留“看起来正确”的自由文本。"""

    if audit_verdict in {"unavailable", "insufficient_evidence"}:
        # 自动 runner 的 failed 与人工“没有观察到答案/证据不够”不是同一个状态。
        return "status_mismatch" if not automated_passed else "unresolved"
    if automated_passed and audit_verdict == "pass":
        return "agree"
    if not automated_passed and audit_verdict == "fail":
        return "agree"
    return "false_positive" if automated_passed else "false_negative"


def apply_audit_verdicts(records: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """把人工协议结果写进 records 副本，并强制每条都有可核查证据与信心等级。"""

    reconciled: list[dict[str, Any]] = []
    for record in records:
        case_id = str(record["identity"]["case_id"])
        finding = verdicts.get(case_id)
        if not isinstance(finding, dict):
            raise ValueError(f"audit verdict missing for case={case_id}")
        verdict = str(finding.get("verdict") or "")
        confidence = str(finding.get("confidence") or "")
        evidence = list(finding.get("evidence") or [])
        reason = str(finding.get("reason") or "")
        root_cause = str(finding.get("root_cause") or "")
        declared_reconciliation = str(finding.get("reconciliation") or "")
        if verdict not in {"pass", "fail", "unavailable", "insufficient_evidence"}:
            raise ValueError(f"audit verdict invalid for case={case_id}: {verdict}")
        if confidence not in {"high", "medium", "low"} or not evidence or not reason or not root_cause:
            raise ValueError(f"audit verdict incomplete for case={case_id}")
        copied = json.loads(json.dumps(record, ensure_ascii=False))
        copied["audit_verdict"] = {
            "verdict": verdict,
            "root_cause": root_cause,
            "reason": reason,
            "evidence": evidence,
            "confidence": confidence,
        }
        inferred_reconciliation = _reconciliation(
            automated_passed=bool(copied["automated_verdict"]["runner_passed_reconstructed"]),
            audit_verdict=verdict,  # type: ignore[arg-type]
        )
        if declared_reconciliation and declared_reconciliation not in {
            "agree", "false_positive", "false_negative", "status_mismatch", "unresolved"
        }:
            raise ValueError(f"audit reconciliation invalid for case={case_id}: {declared_reconciliation}")
        # 少数情况自动 pass/fail 表面相同、但实际检查了错误的对象；显式 status mismatch 保留这种证据。
        copied["reconciliation"] = declared_reconciliation or inferred_reconciliation
        reconciled.append(copied)
    return reconciled


def summarize_reconciliation(records: list[dict[str, Any]]) -> dict[str, Any]:
    """同时按 raw case 与语义组汇总；同组多个 check 绝不冒充多个独立问题。"""

    if any(record.get("audit_verdict") is None for record in records):
        raise ValueError("cannot summarize an audit pack with pending verdicts")
    raw = Counter(str(record["reconciliation"]) for record in records)
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(record["identity"]["semantic_group_id"]), []).append(record)
    group_statuses: list[str] = []
    for group_records in groups.values():
        statuses = {str(record["reconciliation"]) for record in group_records}
        group_statuses.append(next(iter(statuses)) if len(statuses) == 1 else "unresolved")
    audit_verdicts = Counter(str(record["audit_verdict"]["verdict"]) for record in records)
    return {
        "raw_case_count": len(records),
        "semantic_group_count": len(groups),
        "reconciliation_by_raw_case": dict(raw),
        "reconciliation_by_semantic_group": dict(Counter(group_statuses)),
        "audit_verdict_counts": dict(audit_verdicts),
        # `needs_action=manual_review` 是旧 triage 对通过 case 的兼容默认，不能拿它当 pending。
        # 审计卷以实际人工 verdict 与 runner 的 review flag 表达三条互不重叠的队列。
        "pipeline_failure_count": sum(record["audit_verdict"]["verdict"] == "fail" for record in records),
        "review_pending_count": sum(
            bool(record["automated_verdict"]["review_required_reconstructed"]) for record in records
        ),
        "external_unavailable_count": sum(record["audit_verdict"]["verdict"] == "unavailable" for record in records),
    }


def write_audit_json(path: Path, *, manifest: AuditRunManifest, records: list[dict[str, Any]]) -> None:
    """写长期结构化产物；Markdown 永远只是这份 record 的展示 adapter。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"manifest": asdict(manifest), "records": records}
    if records and records[0].get("audit_verdict") is not None:
        payload["reconciliation_summary"] = summarize_reconciliation(records)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_audit_markdown(path: Path, *, manifest: AuditRunManifest, records: list[dict[str, Any]]) -> None:
    """将结构化审计记录渲染给人读；完整 SQL 用代码块，避免 Markdown 表格截断证据。"""

    lines = ["# M26 Diagnostic Human Audit Pack", "", "## Frozen Run", ""]
    lines.extend([f"- run_id: `{manifest.run_id}`", f"- case_contract_version: `{manifest.case_contract_version}`", f"- case_count: {manifest.case_count}"])
    lines.extend(["", "| input | path | sha256 | bytes |", "|---|---|---|---:|"])
    for item in manifest.inputs:
        lines.append(f"| {item.label} | `{item.path}` | `{item.sha256}` | {item.byte_count} |")
    if records and records[0].get("audit_verdict") is not None:
        summary = summarize_reconciliation(records)
        lines.extend(["", "## Reconciliation Summary", "", f"- raw_case_count: {summary['raw_case_count']}", f"- semantic_group_count: {summary['semantic_group_count']}", f"- raw_case: {summary['reconciliation_by_raw_case']}", f"- semantic_group: {summary['reconciliation_by_semantic_group']}", f"- pipeline_failure / review_pending / external_unavailable: {summary['pipeline_failure_count']} / {summary['review_pending_count']} / {summary['external_unavailable_count']}"])
    for record in records:
        identity = record["identity"]
        pipeline = record["pipeline_evidence"]
        result = record["result_evidence"]
        auto = record["automated_verdict"]
        lines.extend(["", f"## {record['position']}. `{identity['case_id']}`", "", f"- semantic_group: `{identity['semantic_group_id']}`", f"- trace_id: `{identity['trace_id']}`", f"- automatic: passed={auto['runner_passed_reconstructed']}, review_required={auto['review_required_reconstructed']}", f"- triage: stage={auto['triage'].get('failure_stage')}, root_cause={auto['triage'].get('primary_root_cause')}, semantic={auto['triage'].get('semantic_status')}", f"- SQL state: `{pipeline['sql_state']}`", "", "### Question Contract", "", record["question_contract"]["question"], "", f"- check: `{record['question_contract']['check_type']}` `{json.dumps(record['question_contract']['check'], ensure_ascii=False)}`", f"- expected tables: `{record['question_contract']['expected_tables']}`", f"- expected alternatives: `{record['question_contract']['expected_tables_alternatives']}`", f"- expected columns: `{record['question_contract']['expected_columns']}`"])
        lines.extend(["", "### Candidate SQL", "", "```sql", pipeline["candidate_sql"] or "-- SQL unavailable; inspect transport_failure_steps below.", "```"])
        lines.extend(["", "### Result / Automatic Evidence", "", f"- columns: `{result['columns']}`", f"- row_count: {result['row_count']}", f"- row_sample: `{json.dumps(result['row_sample'], ensure_ascii=False)}`", f"- score details: `{json.dumps(result['automatic_score_details'], ensure_ascii=False)}`", f"- transport failure steps: `{json.dumps(pipeline['transport_failure_steps'], ensure_ascii=False)}`"])
        if record.get("audit_verdict") is not None:
            audit = record["audit_verdict"]
            lines.extend(["", "### Human Audit", "", f"- verdict: **{audit['verdict']}**", f"- reconciliation: **{record['reconciliation']}**", f"- root_cause: `{audit['root_cause']}`", f"- confidence: `{audit['confidence']}`", f"- reason: {audit['reason']}", f"- evidence: `{audit['evidence']}`"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
