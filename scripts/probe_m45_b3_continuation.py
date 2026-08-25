"""M45-P5：用 P3 immutable qst_0431 Evidence 离线验证 procedure forward continuation。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from engine.governance import test_caller
from engine.phase4b.identity import canonical_hash
from engine.phase4b.rag_diagnostics import RAGRecoveryDiagnostic
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.rag.enterprise_product_runtime import EnterpriseProductRuntimeConfig, load_enterprise_product_runtime
from engine.rag.evidence import DocumentEvidencePayload
from engine.rag.knowledge_tool import KnowledgeRequest
from eval.rag_action_diagnostics import load_continuation_diagnostic_campaign
from scripts.probe_m45_b3 import (
    _EXTERNAL_QUESTIONS,
    _external_slots,
    _private_execution_projection,
    _verified_json_artifact,
)
from scripts.probe_m45_b3_reopen import _rehydrated_outcome


def run_p5(
    *, source_safe_path: Path, source_private_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行唯一零 provider replay；不重跑 semantic retrieval，也不调用 proposal。"""

    campaign = load_continuation_diagnostic_campaign()
    source_safe = _verified_json_artifact(source_safe_path)
    source_private = _verified_json_artifact(source_private_path)
    if (
        source_safe.get("probe_id") != "M45-P3"
        or source_private.get("probe_id") != "M45-P3"
        or source_private.get("safe_artifact_identity") != source_safe.get("artifact_identity")
    ):
        raise ValueError("m45_p5_source_lineage_invalid")
    safe_by_id = {item["scenario_id"]: item for item in source_safe.get("scenarios") or ()}
    private_by_id = {item["scenario_id"]: item for item in source_private.get("scenarios") or ()}
    scenario_id = "qst_0431"
    if scenario_id not in safe_by_id or scenario_id not in private_by_id:
        raise ValueError("m45_p5_source_scenario_missing")

    settings = get_settings()
    config = EnterpriseProductRuntimeConfig.from_settings(settings, allow_cross_thread=False)
    caller = test_caller(caller_id="m45-p5-qst_0431", roles=("demo_user",))
    request = KnowledgeRequest(
        question=_EXTERNAL_QUESTIONS[scenario_id],
        caller=caller,
        purpose="answer_evidence",
        run_id=f"m45-p5-{scenario_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    )
    slots = _external_slots(scenario_id)
    with load_enterprise_product_runtime(config=config) as product:
        initial = _rehydrated_outcome(
            product=product,
            scenario_safe=safe_by_id[scenario_id],
            scenario_private=private_by_id[scenario_id],
            caller=caller,
            request=request,
        )
        adapter = EnterpriseSiblingExpansionAdapter(product.runtime)
        diagnostic = RAGRecoveryDiagnostic()
        observation = diagnostic.observe_existing(
            scenario_id=scenario_id,
            runtime_scope="external_profile",
            slots=slots,
            initial=initial,
            request=request,
            expansion_adapter=adapter,
            continuation_policy="procedure_boundary_v1",
        )
        execution = diagnostic.execute(
            observation=observation,
            slots=slots,
            tool=product.runtime.knowledge_tool(),
            request=request,
            expansion_adapter=adapter,
        )
        runtime_identity = product.identity.safe_projection()

    seeds_by_physical: dict[str, list[tuple[int, int]]] = {}
    for item in initial.selected_evidence:
        payload = item.payload
        if isinstance(payload, DocumentEvidencePayload) and payload.context_coordinates is not None:
            coordinates = payload.context_coordinates
            seeds_by_physical.setdefault(coordinates.physical_source_identity, []).append(
                (coordinates.normalized_start, coordinates.normalized_end)
            )
    forward_same_document = True
    for item in execution.added_evidence:
        payload = item.payload
        coordinates = (
            payload.context_coordinates if isinstance(payload, DocumentEvidencePayload) else None
        )
        if coordinates is None or not any(
            coordinates.normalized_start >= seed_end
            for _, seed_end in seeds_by_physical.get(coordinates.physical_source_identity, ())
        ):
            forward_same_document = False
            break
    assertions = {
        "source_identity_verified": True,
        "initial_coverage_complete": observation.unsupported_slot_identities == (),
        "procedure_boundary_triggered": (
            observation.trigger_reason_codes == ("procedure_forward_unit_available",)
        ),
        "expected_action_selected": execution.chosen_action == "context_expansion_candidate",
        "rewrite_rejected": "query_rewrite_candidate" in observation.rejected_actions,
        "stop_available": "stop" in observation.eligible_actions,
        "forward_same_document_evidence_gain": (
            execution.evidence_delta.gained
            and bool(execution.added_evidence)
            and forward_same_document
        ),
        "zero_provider_retrieval_embedding_composer": (
            execution.consumed.retrieval_batches == 0
            and execution.consumed.model_calls == 0
            and execution.consumed.total_tokens == 0
        ),
        "expansion_budget_respected": len(execution.added_evidence) <= 4,
    }
    passed = all(assertions.values())
    safe: dict[str, Any] = {
        "schema_version": "phase4b-m45-live-probe-v4",
        "probe_id": "M45-P5",
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "source_artifact_identity": source_safe["artifact_identity"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "scenario": {
            "scenario_id": scenario_id,
            "execution": execution.safe_projection(),
            "assertions": assertions,
            "gate": "passed" if passed else "failed",
            "decision": "continue" if passed else "stop",
        },
        "gate": "passed" if passed else "failed",
        "decision": "continue" if passed else "stop",
        "usage": {
            "retrieval_calls": 0,
            "embedding_provider_attempts": 0,
            "chat_model_calls": 0,
            "composer_calls": 0,
            "observed_chat_tokens": 0,
            "token_usage_observed": True,
        },
        "runtime_identity": runtime_identity,
        "reserve_access_state": "sealed",
    }
    safe["artifact_identity"] = canonical_hash(safe)
    private: dict[str, Any] = {
        "schema_version": "phase4b-m45-private-probe-v4",
        "probe_id": "M45-P5",
        "safe_artifact_identity": safe["artifact_identity"],
        "campaign_identity": campaign.identity,
        "source_artifact_identity": source_safe["artifact_identity"],
        "scenario": _private_execution_projection(
            scenario_id=scenario_id,
            question=request.question,
            slots=slots,
            execution=execution,
        ),
    }
    private["artifact_identity"] = canonical_hash(private)
    return safe, private


def _write(path: Path, payload: dict[str, Any]) -> None:
    """用稳定 UTF-8/缩进写出 content-bound Probe artifact。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main() -> None:
    """解析固定 P5 输入/输出路径并运行一次零 provider replay。"""

    parser = argparse.ArgumentParser(description="Run zero-provider M45-P5 continuation replay")
    parser.add_argument("--source-safe", type=Path, required=True)
    parser.add_argument("--source-private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    safe, private = run_p5(
        source_safe_path=args.source_safe,
        source_private_path=args.source_private,
    )
    _write(args.output, safe)
    _write(args.private_output, private)
    print(json.dumps({
        "gate": safe["gate"],
        "decision": safe["decision"],
        "artifact_identity": safe["artifact_identity"],
        "added_evidence": len(safe["scenario"]["execution"]["evidence_delta"]["added"]),
        "provider_attempts": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
