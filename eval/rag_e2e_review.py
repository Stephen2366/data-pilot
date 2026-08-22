"""M41 RAG Eval 的离线人工复核、来源校验与严格可比对照。"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from eval.rag_e2e_contracts import RAGEvalContractError, validate_completed_artifact


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


def compare_completed(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """只比较同 catalog/protocol/runtime/scorer；候选变量不同须另建显式实验合同。"""

    # 步骤 1：先证明两边都是各自闭合的 completed artifact =============================
    validate_completed_artifact(left)
    validate_completed_artifact(right)
    left_spec, right_spec = left["run_spec"], right["run_spec"]
    # 步骤 2：只忽略 run_id；所有影响实验语义的 identity 都必须相同 ---------------------
    comparable_fields = (
        "catalog_identity", "selector_identity", "selected_scenario_ids", "replicate_count",
        "runtime", "assertion_plan", "scorer_identity",
    )
    mismatches = [field for field in comparable_fields if left_spec.get(field) != right_spec.get(field)]
    if mismatches:
        raise RAGEvalContractError("rag_compare_not_comparable", f"identity 不同: {mismatches}")
    # 步骤 3：严格可比后才允许计算右减左的 assertion 变化 -------------------------------
    def status_counts(payload: Mapping[str, Any]) -> dict[str, int]:
        return {name: sum(item["status"] == name for item in payload["assertions"]) for name in ("passed", "failed", "not_observed")}
    l_counts, r_counts = status_counts(left), status_counts(right)
    return {
        "format": "phase4-rag-e2e-compare-v1",
        "strictly_comparable": True,
        "left": {"run_id": left_spec["run_id"], "artifact_identity": left["artifact_identity"], "gate": left["gate"], "assertions": l_counts},
        "right": {"run_id": right_spec["run_id"], "artifact_identity": right["artifact_identity"], "gate": right["gate"], "assertions": r_counts},
        "delta": {key: r_counts[key] - l_counts[key] for key in l_counts},
    }
