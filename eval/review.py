"""M27 的人工证据复核 module。

它不是 scorer，也不是第二个 Gate：自动评测已经结束后，本 module 只把 completed EvalRun、短期
checkpoint 和 canonical Scenario 合同组装为一个脱敏 review bundle，供 Codex 或人工逐题复核。
这样调用方只需要认识 ``build_review_bundle`` / ``apply_review_verdicts`` 两个 Interface，而不用
知道 checkpoint 文件名、旧 M26 triage 或各 assertion 的内部 JSON 形状。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal

from eval.contracts import CONTRACT_VERSION, Catalog, ResultMatchSpec


REVIEW_BUNDLE_SCHEMA_VERSION = "m27-review-bundle-v2"
ReviewVerdict = Literal["pass", "fail", "insufficient_evidence"]
Confidence = Literal["high", "medium", "low"]
ReviewCategory = Literal[
    "confirmed_correct",
    "safety_block_correct",
    "expected_rejection_correct",
    "business_sql_error",
    "output_contract_error",
    "schema_context_error",
    "execution_evidence_unavailable",
    "other_contract_error",
]

_PROTECTED_KEYS = {"email", "phone", "authorization", "api_key", "token", "password"}
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_PATTERN = re.compile(r"(?<!\d)1\d{10}(?!\d)")
_SQL_SECRET_LITERAL_PATTERN = re.compile(
    r"(?i)(\b(?:email|phone|authorization|api_key|token|password)\b\s*=\s*)(?:'[^']*'|\"[^\"]*\"|[^,\s)]+)"
)


def build_review_bundle(
    *,
    run_id: str,
    catalog: Catalog,
    artifact_path: Path,
    checkpoint_root: Path,
    reviewer: str = "codex",
    max_result_rows: int = 3,
) -> dict[str, Any]:
    """把一个 completed M27 run 组装为可复核、但不含完整业务结果的 bundle。

    completed artifact 是长期事实源，但为安全不保存 SQL/rows；短期 checkpoint 才有候选 SQL
    和有限结果证据。两者与 catalog 的 scenario/replicate identity 必须逐条对齐，缺任一证据
    就明确失败，不用 artifact 的 pass/fail 猜造人工审查材料。
    """

    if max_result_rows < 1:
        raise ValueError("max_result_rows must be positive")
    artifact = _load_json_object(artifact_path, label="artifact")
    _validate_artifact(artifact, run_id=run_id)
    scenarios = {item.scenario_id: item for item in catalog.scenarios}
    records: list[dict[str, Any]] = []
    for artifact_run in artifact.get("scenario_runs", []):
        if not isinstance(artifact_run, dict):
            raise ValueError("artifact scenario_runs must contain objects")
        scenario_id = str(artifact_run.get("scenario_id", ""))
        replicate_id = artifact_run.get("replicate_id")
        if scenario_id not in scenarios or not isinstance(replicate_id, int):
            raise ValueError(f"artifact scenario identity is invalid: {scenario_id!r}/{replicate_id!r}")
        checkpoint_path = _checkpoint_path(checkpoint_root, run_id, scenario_id, replicate_id)
        checkpoint = _load_json_object(checkpoint_path, label="checkpoint")
        _validate_checkpoint(checkpoint, run_id=run_id, scenario_id=scenario_id, replicate_id=replicate_id)
        record = _build_record(scenarios[scenario_id], artifact_run, checkpoint, max_result_rows)
        record["source_checkpoint"] = {
            "path": str(checkpoint_path),
            "sha256": _sha256_file(checkpoint_path),
        }
        records.append(record)
    if not records:
        raise ValueError("completed artifact has no scenario runs to review")
    return {
        "review_bundle_schema_version": REVIEW_BUNDLE_SCHEMA_VERSION,
        "reviewer": reviewer,
        "source": {
            "run_id": run_id,
            "contract_version": artifact["contract_version"],
            "artifact_schema_version": artifact["artifact_schema_version"],
            "catalog_hash": artifact["catalog_hash"],
            "selected_contract_hash": artifact["selected_contract_hash"],
            "artifact_path": str(artifact_path),
            "artifact_sha256": _sha256_file(artifact_path),
            "checkpoint_root": str(checkpoint_root),
        },
        "records": records,
    }


def verify_review_bundle_sources(bundle: dict[str, Any]) -> dict[str, int]:
    """校验 review bundle 引用的 artifact/checkpoint 从生成后没有被悄悄替换。

    review 是旁路证据，哈希不为它增加评分权力；它只让复核者能确认眼前 SQL/结果预览仍来自
    当时那个 completed EvalRun。任一短期 checkpoint 被清理、改写或换成别的文件都会明确失败。
    """

    if bundle.get("review_bundle_schema_version") != REVIEW_BUNDLE_SCHEMA_VERSION:
        raise ValueError("unsupported review bundle schema")
    source = bundle.get("source")
    if not isinstance(source, dict):
        raise ValueError("review bundle source must be an object")
    artifact_path = Path(str(source.get("artifact_path", "")))
    _verify_file_hash(artifact_path, source.get("artifact_sha256"), label="artifact")
    records = bundle.get("records")
    if not isinstance(records, list):
        raise ValueError("review bundle records must be a list")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("review bundle records must contain objects")
        checkpoint = record.get("source_checkpoint")
        if not isinstance(checkpoint, dict):
            raise ValueError(f"review checkpoint source missing: {record.get('scenario_id')}")
        _verify_file_hash(
            Path(str(checkpoint.get("path", ""))),
            checkpoint.get("sha256"),
            label=f"checkpoint for {record.get('scenario_id')}",
        )
    return {"artifact": 1, "checkpoints": len(records)}


def apply_review_verdicts(bundle: dict[str, Any], verdicts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """为每个 logical Scenario 写入独立人工 verdict，绝不修改自动评测事实。"""

    if bundle.get("review_bundle_schema_version") != REVIEW_BUNDLE_SCHEMA_VERSION:
        raise ValueError("unsupported review bundle schema")
    copied = deepcopy(bundle)
    records = copied.get("records")
    if not isinstance(records, list):
        raise ValueError("review bundle records must be a list")
    expected_ids = {str(record.get("scenario_id", "")) for record in records}
    if set(verdicts) != expected_ids:
        raise ValueError("review verdicts must cover exactly the bundle scenario ids")
    for record in records:
        scenario_id = str(record["scenario_id"])
        supplied = verdicts[scenario_id]
        verdict = supplied.get("verdict")
        confidence = supplied.get("confidence")
        category = supplied.get("category")
        reason = supplied.get("reason")
        evidence = supplied.get("evidence")
        if verdict not in {"pass", "fail", "insufficient_evidence"}:
            raise ValueError(f"invalid review verdict for {scenario_id}: {verdict!r}")
        if confidence not in {"high", "medium", "low"}:
            raise ValueError(f"invalid review confidence for {scenario_id}: {confidence!r}")
        _validate_review_category(record, verdict, category)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"review reason is required for {scenario_id}")
        if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
            raise ValueError(f"review evidence must be a non-empty string list for {scenario_id}")
        record["review_verdict"] = {
            "verdict": verdict,
            "confidence": confidence,
            "category": category,
            "reason": _redact_text(reason),
            "evidence": [_redact_text(item) for item in evidence],
        }
        record["reconciliation"] = _reconciliation(str(record["automatic_outcome"]), verdict)
    copied["review_summary"] = _review_summary(records)
    return copied


def write_review_json(bundle: dict[str, Any], path: Path) -> None:
    """原子写入 review bundle；它是 EvalRun 的旁路证据，不会覆盖原 artifact。"""

    _write_atomic(path, bundle)


def write_review_markdown(bundle: dict[str, Any], path: Path) -> None:
    """渲染给 Codex/人工阅读的逐题复核材料，不把它反向作为自动 scorer 输入。"""

    source = bundle.get("source", {})
    lines = [
        "# DataPilot M27 Review Bundle",
        "",
        f"- run_id: `{source.get('run_id', '')}`",
        f"- reviewer: `{bundle.get('reviewer', '')}`",
        f"- review_bundle_schema_version: `{bundle.get('review_bundle_schema_version', '')}`",
        "- 说明：本文件是独立人工/Codex 复核证据，不改变 EvalRun、自动分母或 Gate。",
    ]
    summary = bundle.get("review_summary")
    if isinstance(summary, dict):
        lines.extend([
            f"- 人工 verdict 汇总：`{json.dumps(summary.get('verdict_counts', {}), ensure_ascii=False)}`",
            f"- 人工分类汇总：`{json.dumps(summary.get('category_counts', {}), ensure_ascii=False)}`",
        ])
    for record in bundle.get("records", []):
        lines.extend([
            "",
            f"## {record['scenario_id']} (replicate {record['replicate_id']})",
            "",
            f"- 题面：{record['question']}",
            f"- 自动结果：**{record['automatic_outcome']}**",
            f"- 执行状态：`{record['execution_status']}`",
            f"- 自动 assertions：{', '.join(record['automatic_assertions'])}",
            f"- 复核限制：`{record['review_policy']['allowed_verdicts']}`；{record['review_policy']['reason']}",
        ])
        candidate_sql = record["review_evidence"].get("candidate_sql")
        if candidate_sql:
            lines.extend(["", "**Candidate SQL**", "", "```sql", candidate_sql, "```"])
        blocked_reason = record["review_evidence"].get("blocked_reason")
        if blocked_reason:
            lines.extend(["", f"- 拒绝原因：{blocked_reason}"])
        references = record["contract"]["reference_sql"]
        if references:
            lines.extend(["", "**Reference SQL**", "", "```sql", "\n\n".join(references), "```"])
        lines.extend(["", f"- candidate rows：{record['review_evidence']['candidate_row_count']}；preview：`{json.dumps(record['review_evidence']['candidate_result_preview'], ensure_ascii=False)}`"])
        if record["review_evidence"]["reference_result_preview"] is not None:
            lines.append(f"- reference rows：{record['review_evidence']['reference_row_count']}；preview：`{json.dumps(record['review_evidence']['reference_result_preview'], ensure_ascii=False)}`")
        review = record.get("review_verdict")
        if review is None:
            lines.append("- 人工复核：`pending`")
        else:
            lines.extend([
                f"- 人工复核：**{review['verdict']}**（{review['confidence']}）",
                f"- 人工分类：`{review['category']}`",
                f"- reconciliation：`{record['reconciliation']}`",
                f"- 原因：{review['reason']}",
                f"- 证据：{', '.join(review['evidence'])}",
            ])
    _write_atomic(path, {"markdown": "\n".join(lines) + "\n"}, text_key="markdown")


def _build_record(scenario: Any, artifact_run: dict[str, Any], checkpoint: dict[str, Any], max_rows: int) -> dict[str, Any]:
    """从同一 Scenario 的合同、自动事实和 checkpoint 原始证据构造一条可读记录。"""

    evidence = checkpoint["evidence"]
    response = evidence.get("response") if isinstance(evidence.get("response"), dict) else {}
    assertions = checkpoint.get("assertion_results") if isinstance(checkpoint.get("assertion_results"), list) else []
    artifact_assertions = artifact_run.get("assertion_results")
    if not isinstance(artifact_assertions, list) or _assertion_identity(assertions) != _assertion_identity(artifact_assertions):
        raise ValueError(f"checkpoint/artifact assertion mismatch: {scenario.scenario_id}")
    references = [item.spec.reference_sql for item in scenario.assertions if isinstance(item.spec, ResultMatchSpec)]
    record = {
        "scenario_id": scenario.scenario_id,
        "replicate_id": checkpoint["replicate_id"],
        "question": _redact_text(scenario.question),
        "user_role": scenario.user_role,
        "classification": scenario.classification,
        "contract": {
            "assertions": [
                {"assertion_id": item.assertion_id, "kind": item.kind, "spec": _sanitize(asdict(item.spec) if item.spec is not None else None)}
                for item in scenario.assertions
            ],
            "authority_refs": list(scenario.authority_refs),
            "reference_sql": [_redact_text(sql) for sql in references],
        },
        "execution_status": evidence.get("execution_status"),
        "automatic_outcome": _automatic_outcome(assertions),
        "automatic_assertions": [f"{item.get('assertion_id')}={item.get('status')}" for item in assertions],
        "review_evidence": {
            "candidate_sql": _optional_text(response.get("sql")),
            "blocked_reason": _optional_text(response.get("blocked_reason")),
            "answer_summary": _optional_text(response.get("answer")),
            "candidate_columns": _sanitize(response.get("columns") or []),
            "candidate_row_count": len(response.get("rows") or []),
            "candidate_result_preview": _preview_rows(response.get("rows"), max_rows),
            "reference_row_count": len(evidence.get("expected_rows") or []) if evidence.get("expected_rows") is not None else None,
            "reference_result_preview": _preview_rows(evidence.get("expected_rows"), max_rows) if evidence.get("expected_rows") is not None else None,
            "trace_summary": _trace_summary(evidence.get("trace_steps") or []),
        },
        "review_verdict": None,
        "reconciliation": None,
    }
    record["review_policy"] = _review_policy(record)
    return record


def _validate_artifact(artifact: dict[str, Any], *, run_id: str) -> None:
    if artifact.get("run_id") != run_id:
        raise ValueError("artifact run_id mismatch")
    if artifact.get("run_status") != "completed":
        raise ValueError("only completed EvalRun may create a review bundle")
    if artifact.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"unsupported review contract: {artifact.get('contract_version')!r}")


def _checkpoint_path(root: Path, run_id: str, scenario_id: str, replicate_id: int) -> Path:
    """集中约束短期 checkpoint 的命名，避免调用方自行拼路径。"""

    return root / run_id / "checkpoints" / f"{scenario_id}--r{replicate_id}.json"


def _validate_checkpoint(checkpoint: dict[str, Any], *, run_id: str, scenario_id: str, replicate_id: int) -> None:
    evidence = checkpoint.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError(f"checkpoint lacks evidence: {scenario_id}")
    actual = (checkpoint.get("scenario_id"), checkpoint.get("replicate_id"), evidence.get("run_id"), evidence.get("scenario_id"), evidence.get("replicate_id"))
    expected = (scenario_id, replicate_id, run_id, scenario_id, replicate_id)
    if actual != expected:
        raise ValueError(f"checkpoint identity mismatch for {scenario_id}")


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    """以流式方式计算文件指纹，不把完整 checkpoint 再复制进内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file_hash(path: Path, expected: Any, *, label: str) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{label} SHA-256 is missing or invalid")
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if _sha256_file(path) != expected:
        raise ValueError(f"{label} SHA-256 mismatch")


def _assertion_identity(assertions: list[dict[str, Any]]) -> list[tuple[Any, Any, Any]]:
    return [(item.get("assertion_id"), item.get("kind"), item.get("status")) for item in assertions if isinstance(item, dict)]


def _automatic_outcome(assertions: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in assertions if isinstance(item, dict)}
    if "failed" in statuses:
        return "failed"
    if statuses == {"passed"}:
        return "passed"
    return "not_observed"


def _reconciliation(automatic: str, manual: ReviewVerdict) -> str:
    manual_name = "manual_insufficient_evidence" if manual == "insufficient_evidence" else f"manual_{manual}"
    return f"auto_{automatic}_{manual_name}"


def _assertion_kinds(record: dict[str, Any]) -> set[str]:
    contract = record.get("contract")
    assertions = contract.get("assertions") if isinstance(contract, dict) else []
    return {str(item.get("kind")) for item in assertions if isinstance(item, dict)}


def _review_policy(record: dict[str, Any]) -> dict[str, str]:
    """把“证据不足不等于 SQL 错”编码为复核者看得见的窄规则。"""

    candidate_sql = record.get("review_evidence", {}).get("candidate_sql")
    assertion_kinds = _assertion_kinds(record)
    if candidate_sql:
        return {"allowed_verdicts": "pass / fail / insufficient_evidence", "reason": "候选 SQL 可供逐题核验。"}
    if assertion_kinds & {"safety_block", "expected_rejection"}:
        return {"allowed_verdicts": "pass / fail / insufficient_evidence", "reason": "此题允许以 Guard 的明确拒绝证据复核，无候选 SQL 不自动代表失败。"}
    return {
        "allowed_verdicts": "insufficient_evidence only",
        "reason": "普通业务题没有 candidate SQL，无法判断答案对错；不得臆测为 pass 或 fail。",
    }


def _validate_review_category(record: dict[str, Any], verdict: Any, category: Any) -> None:
    """验证 verdict 与分类、合同和可见证据互相不矛盾。"""

    allowed_by_verdict = {
        "pass": {"confirmed_correct", "safety_block_correct", "expected_rejection_correct"},
        "fail": {"business_sql_error", "output_contract_error", "schema_context_error", "other_contract_error"},
        "insufficient_evidence": {"execution_evidence_unavailable"},
    }
    if verdict not in allowed_by_verdict or category not in allowed_by_verdict[verdict]:
        raise ValueError(f"invalid review category for {record['scenario_id']}: {category!r}")
    policy = record.get("review_policy")
    if isinstance(policy, dict) and policy.get("allowed_verdicts") == "insufficient_evidence only" and verdict != "insufficient_evidence":
        raise ValueError(f"ordinary scenario without candidate SQL requires insufficient_evidence: {record['scenario_id']}")
    kinds = _assertion_kinds(record)
    if category == "safety_block_correct" and "safety_block" not in kinds:
        raise ValueError(f"safety_block_correct requires safety_block contract: {record['scenario_id']}")
    if category == "expected_rejection_correct" and "expected_rejection" not in kinds:
        raise ValueError(f"expected_rejection_correct requires expected_rejection contract: {record['scenario_id']}")


def _review_summary(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """汇总旁路复核标签，方便定位，不参与任何自动评分或 Gate。"""

    verdict_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    reconciliation_counts: dict[str, int] = {}
    for record in records:
        review = record.get("review_verdict")
        if not isinstance(review, dict):
            continue
        for counts, value in (
            (verdict_counts, review["verdict"]),
            (category_counts, review["category"]),
            (reconciliation_counts, record["reconciliation"]),
        ):
            counts[value] = counts.get(value, 0) + 1
    return {
        "verdict_counts": verdict_counts,
        "category_counts": category_counts,
        "reconciliation_counts": reconciliation_counts,
    }


def _preview_rows(value: Any, max_rows: int) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    return [_sanitize(item) for item in rows[:max_rows] if isinstance(item, dict)]


def _trace_summary(steps: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        metadata = step.get("metadata") if isinstance(step.get("metadata"), dict) else {}
        result.append({
            "step_type": step.get("step_type") or step.get("name"),
            "status": step.get("status"),
            "error_type": step.get("error_type"),
            "metadata": _sanitize({key: metadata[key] for key in {"tables", "fields", "metrics", "relation_ids", "relations", "plan_steps", "issue_tags", "errors", "blocked_via", "row_count", "column_count", "error_subtype"} & set(metadata)}),
        })
    return result


def _sanitize(value: Any, key: str = "") -> Any:
    if key.lower() in _PROTECTED_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): _sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    redacted = _EMAIL_PATTERN.sub("[redacted-email]", value)
    redacted = _PHONE_PATTERN.sub("[redacted-phone]", redacted)
    return _SQL_SECRET_LITERAL_PATTERN.sub(r"\1'[redacted]'", redacted)


def _optional_text(value: Any) -> str | None:
    """把 JSON 的 null 保留为空，而不是把它误展示为用户可见的 ``None``。"""

    if value is None:
        return None
    text = _redact_text(str(value))
    return text or None


def _write_atomic(path: Path, payload: dict[str, Any], *, text_key: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    text = payload[text_key] if text_key is not None else json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
