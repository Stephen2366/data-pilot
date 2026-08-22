"""M41 RAG Eval 的离线人工复核、来源校验与严格可比对照。"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from eval.rag_e2e_contracts import RAGEvalContractError, canonical_hash, validate_completed_artifact


REVIEW_FORMAT = "phase4-rag-e2e-review-v1"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RAGEvalContractError("rag_review_source_invalid", str(path))
    return payload


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_review_bundle(*, artifact_path: Path, checkpoint_root: Path, reviewer: str) -> dict[str, Any]:
    """只读 completed artifact/checkpoint；不执行产品链路，也不修改自动 Gate。"""

    artifact = _load(artifact_path)
    validate_completed_artifact(artifact)
    spec = artifact["run_spec"]
    run_id = str(spec["run_id"])
    scenario_metadata = {str(key): dict(value) for key, value in spec.get("scenario_metadata") or ()}
    assertions: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for item in artifact["assertions"]:
        assertions.setdefault((str(item["scenario_id"]), int(item["replicate"])), []).append(item)
    records: list[dict[str, Any]] = []
    for execution in artifact["executions"]:
        scenario_id = str(execution["scenario_id"])
        replicate = int(execution["replicate"])
        checkpoint = checkpoint_root / run_id / "checkpoints" / f"{scenario_id}-r{replicate}.json"
        raw = _load(checkpoint)
        if raw.get("run_spec_identity") != artifact["run_spec_identity"] or raw.get("execution") != execution:
            raise RAGEvalContractError("rag_review_checkpoint_mismatch", f"{scenario_id}/r{replicate}")
        records.append({
            "record_id": f"{scenario_id}:r{replicate}",
            "scenario_id": scenario_id,
            "replicate": replicate,
            "reference": scenario_metadata.get(scenario_id, {}),
            "automatic_assertions": assertions[(scenario_id, replicate)],
            "answer": execution.get("answer"),
            "citations": execution.get("citations") or [],
            "docs_used": execution.get("docs_used") or [],
            "funnel_document_keys": execution.get("stage_document_keys") or [],
            "provider_attempts": execution.get("provider_attempts") or [],
            "review_policy": "自然语言 correctness/completeness 必须结合引用证据人工判断；自动 terms 只提供下限。",
            "source_checkpoint": {"path": str(checkpoint), "sha256": _file_hash(checkpoint)},
            "verdict": None,
        })
    return {
        "format": REVIEW_FORMAT,
        "reviewer": reviewer,
        "source": {
            "artifact_path": str(artifact_path),
            "artifact_sha256": _file_hash(artifact_path),
            "artifact_identity": artifact["artifact_identity"],
            "run_id": run_id,
        },
        "records": records,
        "boundary": "旁路人工证据；不修改自动 artifact、assertion 分母或 Gate。",
    }


def verify_review_sources(bundle: Mapping[str, Any]) -> dict[str, int]:
    """重算 artifact/checkpoint SHA-256，防止人工复核引用被替换的答卷。"""

    if bundle.get("format") != REVIEW_FORMAT:
        raise RAGEvalContractError("rag_review_invalid", "review format 不匹配")
    source = bundle.get("source")
    if not isinstance(source, Mapping):
        raise RAGEvalContractError("rag_review_invalid", "source 缺失")
    artifact_path = Path(str(source.get("artifact_path") or ""))
    if not artifact_path.is_file() or _file_hash(artifact_path) != source.get("artifact_sha256"):
        raise RAGEvalContractError("rag_review_hash_mismatch", "artifact 来源已变化")
    records = bundle.get("records")
    if not isinstance(records, list):
        raise RAGEvalContractError("rag_review_invalid", "records 非列表")
    for record in records:
        checkpoint = record.get("source_checkpoint") if isinstance(record, Mapping) else None
        path = Path(str(checkpoint.get("path") or "")) if isinstance(checkpoint, Mapping) else Path("")
        if not path.is_file() or _file_hash(path) != checkpoint.get("sha256"):
            raise RAGEvalContractError("rag_review_hash_mismatch", f"checkpoint 来源已变化: {path}")
    return {"artifact": 1, "checkpoints": len(records)}


def apply_verdicts(bundle: Mapping[str, Any], verdicts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """verdict 必须逐 execution 闭集覆盖，并与自动结果并列保存。"""

    verify_review_sources(bundle)
    copied = deepcopy(dict(bundle))
    expected = {str(item["record_id"]) for item in copied["records"]}
    if set(verdicts) != expected:
        raise RAGEvalContractError("rag_review_verdict_mismatch", "verdict 必须精确覆盖 review records")
    counts = {"pass": 0, "fail": 0, "insufficient_evidence": 0}
    for record in copied["records"]:
        verdict = dict(verdicts[record["record_id"]])
        name = verdict.get("verdict")
        if name not in counts or not str(verdict.get("reason") or "").strip():
            raise RAGEvalContractError("rag_review_verdict_invalid", record["record_id"])
        counts[name] += 1
        record["verdict"] = verdict
    copied["review_summary"] = counts
    return copied


def _primary_stage(assertions: list[Mapping[str, Any]]) -> str:
    """从 artifact 内已有 assertion 重建首个失败层，不重新执行 scorer。"""

    priority = (
        ("product_runtime", {"route_correct", "axes_correct", "reason_correct", "graph_path_correct", "rag_tool_once", "response_trace_consistent", "runtime_identity_complete"}),
        ("retrieval", {"retrieved_gold"}),
        ("selection", {"selected_gold"}),
        ("generation_context", {"generation_visible_gold"}),
        ("provider_or_support", {"provider_observed", "composer_support_valid", "no_generation"}),
        ("citation", {"cited_gold"}),
        ("answer", {"answer_present", "answer_absent", "safe_fallback_answer", "required_answer_terms", "forbidden_terms_absent"}),
    )
    failed_ids = {str(item["assertion_id"]) for item in assertions if item["status"] == "failed"}
    for stage, ids in priority:
        if failed_ids & ids:
            return stage
    return "not_observed" if any(item["status"] == "not_observed" for item in assertions) else "passed"


def _latency_summary(payload: Mapping[str, Any]) -> dict[str, float | int | None]:
    """比较已保存的 AnswerFlow elapsed_ms；缺字段时诚实返回 count=0。"""

    values = sorted(
        float(item.get("rag_diagnostics", {}).get("elapsed_ms"))
        for item in payload["executions"]
        if item.get("rag_diagnostics", {}).get("elapsed_ms") is not None
    )
    if not values:
        return {"count": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None}

    def percentile(fraction: float) -> float:
        index = min(len(values) - 1, max(0, int((len(values) - 1) * fraction + 0.5)))
        return round(values[index], 3)

    return {
        "count": len(values),
        "mean_ms": round(sum(values) / len(values), 3),
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
    }


def compare_completed(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    allowed_runtime_differences: tuple[str, ...] = (),
) -> dict[str, Any]:
    """默认严格比较；显式声明 runtime 字段后才允许候选 A/B。"""

    # 步骤 1：先证明两边都是各自闭合的 completed artifact =============================
    validate_completed_artifact(left)
    validate_completed_artifact(right)
    allowed_runtime_differences = tuple(sorted(set(allowed_runtime_differences)))
    left_spec, right_spec = left["run_spec"], right["run_spec"]
    # 步骤 2：题集、协议和 scorer 永远相同；runtime 只允许预注册字段变化。--------------
    comparable_fields = (
        "catalog_identity", "selector_identity", "selected_scenario_ids", "replicate_count",
        "assertion_plan", "scorer_identity", "scenario_metadata",
    )
    mismatches = [field for field in comparable_fields if left_spec.get(field) != right_spec.get(field)]
    if mismatches:
        raise RAGEvalContractError("rag_compare_not_comparable", f"identity 不同: {mismatches}")
    left_runtime, right_runtime = dict(left_spec.get("runtime") or {}), dict(right_spec.get("runtime") or {})
    known_runtime_fields = set(left_runtime) & set(right_runtime)
    unknown_allowed = set(allowed_runtime_differences) - known_runtime_fields
    if unknown_allowed:
        raise RAGEvalContractError(
            "rag_compare_allowed_difference_unknown", f"未知 runtime 字段: {sorted(unknown_allowed)}"
        )
    runtime_differences = tuple(
        sorted(key for key in set(left_runtime) | set(right_runtime) if left_runtime.get(key) != right_runtime.get(key))
    )
    undeclared = set(runtime_differences) - set(allowed_runtime_differences)
    if undeclared:
        raise RAGEvalContractError(
            "rag_compare_not_comparable", f"未声明的 runtime 差异: {sorted(undeclared)}"
        )

    # 步骤 3：在相同 execution/assertion 闭集上做 paired compare。----------------------
    def status_counts(payload: Mapping[str, Any]) -> dict[str, int]:
        return {name: sum(item["status"] == name for item in payload["assertions"]) for name in ("passed", "failed", "not_observed")}
    l_counts, r_counts = status_counts(left), status_counts(right)
    metadata = {str(key): dict(value) for key, value in right_spec.get("scenario_metadata") or ()}
    left_assertions: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    right_assertions: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for target, payload in ((left_assertions, left), (right_assertions, right)):
        for item in payload["assertions"]:
            target.setdefault((str(item["scenario_id"]), int(item["replicate"])), []).append(item)
    paired: list[dict[str, Any]] = []
    verdict_counts: Counter[str] = Counter()
    primary_transitions: Counter[str] = Counter()
    difficulty_assertions: dict[str, dict[str, Counter[str]]] = {}
    for key in left_assertions:
        before = {str(item["assertion_id"]): str(item["status"]) for item in left_assertions[key]}
        after = {str(item["assertion_id"]): str(item["status"]) for item in right_assertions[key]}
        if before.keys() != after.keys():
            raise RAGEvalContractError("rag_compare_not_comparable", f"assertion 闭集漂移: {key}")
        transitions = Counter(f"{before[name]}->{after[name]}" for name in before)
        has_unknown_transition = any(
            before[name] != after[name] and "not_observed" in {before[name], after[name]} for name in before
        )
        improved = transitions["failed->passed"]
        regressed = transitions["passed->failed"]
        if has_unknown_transition:
            verdict = "insufficient"
        elif improved and regressed:
            verdict = "mixed"
        elif improved:
            verdict = "win"
        elif regressed:
            verdict = "loss"
        else:
            verdict = "tie"
        verdict_counts[verdict] += 1
        left_primary = _primary_stage(left_assertions[key])
        right_primary = _primary_stage(right_assertions[key])
        primary_transitions[f"{left_primary}->{right_primary}"] += 1
        difficulty = str(metadata.get(key[0], {}).get("difficulty") or "not_applicable")
        bucket = difficulty_assertions.setdefault(
            difficulty, {"left": Counter(), "right": Counter(), "delta": Counter()}
        )
        for name in ("passed", "failed", "not_observed"):
            left_value = sum(value == name for value in before.values())
            right_value = sum(value == name for value in after.values())
            bucket["left"][name] += left_value
            bucket["right"][name] += right_value
            bucket["delta"][name] += right_value - left_value
        paired.append({
            "record_id": f"{key[0]}:r{key[1]}",
            "difficulty": difficulty,
            "verdict": verdict,
            "assertion_transitions": dict(sorted(transitions.items())),
            "primary_transition": f"{left_primary}->{right_primary}",
        })

    def usage(payload: Mapping[str, Any]) -> dict[str, int]:
        totals: Counter[str] = Counter()
        for execution in payload["executions"]:
            totals.update({str(key): int(value) for key, value in execution.get("provider_usage", {}).items()})
        return dict(sorted(totals.items()))

    left_usage, right_usage = usage(left), usage(right)
    usage_keys = set(left_usage) | set(right_usage)
    experiment = {
        "allowed_runtime_differences": list(allowed_runtime_differences),
        "actual_runtime_differences": list(runtime_differences),
        "shared_catalog_identity": left_spec["catalog_identity"],
        "shared_selector_identity": left_spec["selector_identity"],
        "shared_scorer_identity": left_spec["scorer_identity"],
    }
    left_latency, right_latency = _latency_summary(left), _latency_summary(right)
    latency_delta = {
        key: (
            None
            if left_latency[key] is None or right_latency[key] is None
            else round(float(right_latency[key]) - float(left_latency[key]), 3)
        )
        for key in ("mean_ms", "p50_ms", "p95_ms")
    }
    return {
        "format": "phase4-rag-e2e-compare-v2",
        "comparison_mode": "candidate" if runtime_differences else "strict_repeat",
        "strictly_comparable": not runtime_differences,
        "experiment_contract": {**experiment, "identity": canonical_hash(experiment)},
        "left": {"run_id": left_spec["run_id"], "artifact_identity": left["artifact_identity"], "gate": left["gate"], "assertions": l_counts},
        "right": {"run_id": right_spec["run_id"], "artifact_identity": right["artifact_identity"], "gate": right["gate"], "assertions": r_counts},
        "delta": {key: r_counts[key] - l_counts[key] for key in l_counts},
        "paired_summary": dict(sorted(verdict_counts.items())),
        "paired_executions": paired,
        "primary_failure_transitions": dict(sorted(primary_transitions.items())),
        "difficulty_assertions": {
            difficulty: {side: dict(counts) for side, counts in views.items()}
            for difficulty, views in sorted(difficulty_assertions.items())
        },
        "provider_usage": {
            "left": left_usage,
            "right": right_usage,
            "delta": {key: right_usage.get(key, 0) - left_usage.get(key, 0) for key in sorted(usage_keys)},
        },
        "answer_flow_latency": {
            "left": left_latency,
            "right": right_latency,
            "delta": latency_delta,
        },
        "interpretation_boundary": (
            "paired verdict 只描述自动 assertion 迁移；自然语言 correctness 仍需并列人工 review。"
        ),
    }
