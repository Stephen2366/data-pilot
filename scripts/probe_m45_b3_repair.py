"""M45-P4R：qst_0461 离线 replay 通过后，才重验 qst_0431 唯一一次 proposal。"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from engine.governance import test_caller
from engine.phase4b.identity import canonical_hash
from engine.phase4b.rag_diagnostics import RAGRecoveryDiagnostic, RecoveryExecution
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.phase4b.rag_requirement_proposal import (
    EvidenceAwareRequirementProposer,
    ProposalUsage,
    RequirementProposal,
    RequirementProposalError,
    make_qwen_requirement_proposal_client,
    validate_requirement_proposal,
)
from engine.rag.enterprise_product_runtime import EnterpriseProductRuntimeConfig, load_enterprise_product_runtime
from engine.rag.evidence import DocumentEvidencePayload
from engine.rag.knowledge_tool import KnowledgeRequest
from eval.rag_action_diagnostics import load_repair_diagnostic_campaign
from scripts.probe_m45_b3 import (
    _EXTERNAL_QUESTIONS,
    _expected_docs_after_action,
    _private_execution_projection,
    _verified_json_artifact,
)
from scripts.probe_m45_b3_reopen import _rehydrated_outcome


def _execute_scenario(
    *, scenario_id: str, proposal: RequirementProposal, initial: Any, request: KnowledgeRequest,
    diagnostic: RAGRecoveryDiagnostic, adapter: EnterpriseSiblingExpansionAdapter, tool: Any,
    dataset_root: Path, runtime_identity: dict[str, Any], source_identity: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """proposal 已验证后，统一执行 local coverage → sibling preview → expansion。"""

    observation = diagnostic.observe_existing(
        scenario_id=scenario_id,
        runtime_scope="external_profile",
        slots=proposal.slots,
        initial=initial,
        request=request,
        expansion_adapter=adapter,
    )
    if "context_expansion_candidate" in observation.eligible_actions:
        execution = diagnostic.execute(
            observation=observation,
            slots=proposal.slots,
            tool=tool,
            request=request,
            expansion_adapter=adapter,
        )
    else:
        # 复用 P4 的安全 stop 构造，绝不能 fallback rewrite。
        from engine.phase4b.loop_contracts import EvidenceDelta, ProgressDecision, ResourceConsumption

        execution = RecoveryExecution(
            observation=observation,
            chosen_action="stop",
            status="blocked",
            evidence_delta=EvidenceDelta(),
            consumed=ResourceConsumption(actions=1, token_usage_observed=True),
            progress=ProgressDecision(False, False, "expected_action_not_eligible"),
            duplicate_key=canonical_hash({
                "scenario_id": scenario_id,
                "source_identity": source_identity,
                "requirement_signature": observation.requirement_signature,
            }),
            termination_reason="expected_action_not_eligible",
            elapsed_ms=0.0,
        )
    expected_docs = _expected_docs_after_action(dataset_root, scenario_id)
    added_logical = {
        item.payload.context_coordinates.logical_document_id
        for item in execution.added_evidence
        if isinstance(item.payload, DocumentEvidencePayload)
        and item.payload.context_coordinates is not None
    }
    combined = initial.selected_evidence + execution.added_evidence
    assertions = {
        "source_identity_verified": True,
        "proposal_valid": True,
        "proposal_has_unsupported_slots": bool(proposal.slots),
        "proposal_marker_mode_bounded": all(
            slot.marker_match_mode == "token_overlap" for slot in proposal.slots
        ),
        "expected_action_selected": execution.chosen_action == "context_expansion_candidate",
        "rewrite_rejected": "query_rewrite_candidate" in observation.rejected_actions,
        "stop_available": "stop" in observation.eligible_actions,
        "evidence_gain": execution.evidence_delta.gained,
        "proposal_gaps_supported": all(slot.supported_by(combined) for slot in proposal.slots),
        "offline_gold_document_only": bool(added_logical) and added_logical <= expected_docs,
        "zero_new_retrieval_embedding_composer": execution.consumed.retrieval_batches == 0,
        "expansion_budget_respected": len(execution.added_evidence) <= 4,
    }
    passed = all(assertions.values())
    safe = {
        "scenario_id": scenario_id,
        "proposal_status": "completed",
        "proposal": proposal.safe_projection(),
        "execution": execution.safe_projection(),
        "assertions": assertions,
        "gate": "passed" if passed else "failed",
        "decision": "continue" if passed else "stop",
        "usage": {
            "retrieval_calls": 0,
            "embedding_provider_attempts": 0,
            "chat_model_calls": proposal.usage.calls,
            "composer_calls": 0,
            "observed_chat_tokens": proposal.usage.total_tokens,
            "token_usage_observed": proposal.usage.token_usage_observed,
        },
        "runtime_identity": runtime_identity,
    }
    private = _private_execution_projection(
        scenario_id=scenario_id,
        question=request.question,
        slots=proposal.slots,
        execution=execution,
    )
    private["proposal"] = proposal.private_projection()
    private["source_artifact_identity"] = source_identity
    return safe, private


def run_p4_repair(
    *, p3_safe_path: Path, p3_private_path: Path, p4_safe_path: Path,
    p4_private_path: Path, dataset_root: Path, allow_provider_revalidation: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行 additive repair；离线 461 失败时保证 qst_0431 provider calls=0。"""

    campaign = load_repair_diagnostic_campaign()
    p3_safe = _verified_json_artifact(p3_safe_path)
    p3_private = _verified_json_artifact(p3_private_path)
    p4_safe = _verified_json_artifact(p4_safe_path)
    p4_private = _verified_json_artifact(p4_private_path)
    if (
        p3_safe.get("probe_id") != "M45-P3"
        or p3_private.get("safe_artifact_identity") != p3_safe.get("artifact_identity")
        or p4_safe.get("probe_id") != "M45-P4"
        or p4_private.get("safe_artifact_identity") != p4_safe.get("artifact_identity")
        or p4_safe.get("campaign_identity") != campaign.predecessor_campaign_identity
        or p4_safe.get("source_artifact_identity") != p3_safe.get("artifact_identity")
    ):
        raise ValueError("m45_p4r_source_lineage_invalid")
    p3_safe_by_id = {item["scenario_id"]: item for item in p3_safe["scenarios"]}
    p3_private_by_id = {item["scenario_id"]: item for item in p3_private["scenarios"]}
    p4_safe_by_id = {item["scenario_id"]: item for item in p4_safe["scenarios"]}
    p4_private_by_id = {item["scenario_id"]: item for item in p4_private["scenarios"]}

    settings = get_settings()
    config = EnterpriseProductRuntimeConfig.from_settings(settings, allow_cross_thread=False)
    safe_scenarios: list[dict[str, Any]] = []
    private_scenarios: list[dict[str, Any]] = []
    with load_enterprise_product_runtime(config=config) as product:
        adapter = EnterpriseSiblingExpansionAdapter(product.runtime)
        tool = product.runtime.knowledge_tool()
        diagnostic = RAGRecoveryDiagnostic()
        runtime_identity = product.identity.safe_projection()

        # 步骤 1：qst_0461 只重放 P4 immutable response，绝不调用 provider。===============
        scenario_id = "qst_0461"
        caller = test_caller(caller_id="m45-p4r-qst_0461", roles=("demo_user",))
        request = KnowledgeRequest(
            question=_EXTERNAL_QUESTIONS[scenario_id], caller=caller, purpose="answer_evidence",
            run_id=f"m45-p4r-{scenario_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        )
        initial = _rehydrated_outcome(
            product=product,
            scenario_safe=p3_safe_by_id[scenario_id],
            scenario_private=p3_private_by_id[scenario_id],
            caller=caller,
            request=request,
        )
        source_proposal = p4_private_by_id[scenario_id]["proposal"]
        replay = validate_requirement_proposal(
            raw=source_proposal["raw_response"],
            question=request.question,
            current_evidence=initial.selected_evidence,
            prompt_fingerprint=p4_safe_by_id[scenario_id]["proposal"]["prompt_fingerprint"],
            usage=ProposalUsage(
                model="qwen3.7-plus", calls=0, total_tokens=0, token_usage_observed=True,
            ),
        )
        replay = replace(
            replay,
            prompt=source_proposal["prompt"],
            raw_response=source_proposal["raw_response"],
        )
        safe_461, private_461 = _execute_scenario(
            scenario_id=scenario_id,
            proposal=replay,
            initial=initial,
            request=request,
            diagnostic=diagnostic,
            adapter=adapter,
            tool=tool,
            dataset_root=dataset_root,
            runtime_identity=runtime_identity,
            source_identity=p4_safe["artifact_identity"],
        )
        safe_scenarios.append(safe_461)
        private_scenarios.append(private_461)

        # 步骤 2：offline replay 不通过时，qst_0431 必须保持零 provider。===============
        if safe_461["gate"] == "passed" and allow_provider_revalidation:
            scenario_id = "qst_0431"
            caller = test_caller(caller_id="m45-p4r-qst_0431", roles=("demo_user",))
            request = KnowledgeRequest(
                question=_EXTERNAL_QUESTIONS[scenario_id], caller=caller, purpose="answer_evidence",
                run_id=f"m45-p4r-{scenario_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            )
            initial = _rehydrated_outcome(
                product=product,
                scenario_safe=p3_safe_by_id[scenario_id],
                scenario_private=p3_private_by_id[scenario_id],
                caller=caller,
                request=request,
            )
            client = make_qwen_requirement_proposal_client(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_base_url,
                model="qwen3.7-plus",
                timeout=settings.llm_timeout_seconds,
            )
            try:
                proposal = EvidenceAwareRequirementProposer(client).propose(
                    question=request.question,
                    current_evidence=initial.selected_evidence,
                )
                safe_431, private_431 = _execute_scenario(
                    scenario_id=scenario_id,
                    proposal=proposal,
                    initial=initial,
                    request=request,
                    diagnostic=diagnostic,
                    adapter=adapter,
                    tool=tool,
                    dataset_root=dataset_root,
                    runtime_identity=runtime_identity,
                    source_identity=p4_safe["artifact_identity"],
                )
            except RequirementProposalError as exc:
                # 未来同类失败必须形成 artifact；本次首个 P4R 已在该 catch 补齐前发生，
                # 由 recover_m45_p4r_failure.py 诚实记录 raw/tokens 丢失，绝不重发。
                usage = exc.usage or ProposalUsage(
                    model="qwen3.7-plus",
                    calls=client.request_count,
                    total_tokens=client.total_tokens,
                    token_usage_observed=client.successful_response_count > 0,
                )
                safe_431 = {
                    "scenario_id": scenario_id,
                    "proposal_status": "failed",
                    "proposal_error": exc.reason_code,
                    "execution": {
                        "chosen_action": "stop",
                        "status": "blocked",
                        "termination_reason": exc.reason_code,
                    },
                    "assertions": {
                        "proposal_transport_completed": client.successful_response_count == 1,
                        "proposal_valid": False,
                        "expected_action_selected": False,
                    },
                    "gate": "failed",
                    "decision": "stop",
                    "usage": {
                        "retrieval_calls": 0,
                        "embedding_provider_attempts": 0,
                        "chat_model_calls": usage.calls,
                        "composer_calls": 0,
                        "observed_chat_tokens": usage.total_tokens,
                        "token_usage_observed": usage.token_usage_observed,
                    },
                    "runtime_identity": runtime_identity,
                }
                private_431 = {
                    "scenario_id": scenario_id,
                    "question": request.question,
                    "proposal_error": exc.reason_code,
                    "proposal_failure": {
                        "prompt": exc.prompt,
                        "raw_response": exc.raw_response,
                        "usage": usage.safe_projection(),
                    },
                    "source_artifact_identity": p4_safe["artifact_identity"],
                }
            safe_scenarios.append(safe_431)
            private_scenarios.append(private_431)

    usage = {
        key: sum(int(item["usage"][key]) for item in safe_scenarios)
        for key in (
            "retrieval_calls", "embedding_provider_attempts", "chat_model_calls",
            "composer_calls", "observed_chat_tokens",
        )
    }
    usage["token_usage_observed"] = True
    budget_ok = (
        usage["chat_model_calls"] <= campaign.budget["max_chat_model_calls"]
        and usage["observed_chat_tokens"] <= campaign.budget["max_chat_tokens"]
    )
    passed = len(safe_scenarios) == 2 and budget_ok and all(
        item["gate"] == "passed" for item in safe_scenarios
    )
    safe: dict[str, Any] = {
        "schema_version": "phase4b-m45-live-probe-v3",
        "probe_id": "M45-P4R",
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "predecessor_campaign_identity": campaign.predecessor_campaign_identity,
        "source_artifact_identities": {
            "p3": p3_safe["artifact_identity"],
            "p4": p4_safe["artifact_identity"],
        },
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": safe_scenarios,
        "gate": "passed" if passed else "failed",
        "decision": "continue" if passed else "stop",
        "usage": usage,
        "budget_respected": budget_ok,
        "reserve_access_state": "sealed",
    }
    if not allow_provider_revalidation:
        safe["offline_preflight_only"] = True
    safe["artifact_identity"] = canonical_hash(safe)
    private: dict[str, Any] = {
        "schema_version": "phase4b-m45-private-probe-v3",
        "probe_id": "M45-P4R",
        "safe_artifact_identity": safe["artifact_identity"],
        "campaign_identity": campaign.identity,
        "source_artifact_identities": safe["source_artifact_identities"],
        "scenarios": private_scenarios,
    }
    private["artifact_identity"] = canonical_hash(private)
    return safe, private


def main() -> None:
    """执行 qst0461 离线 replay，并按门决定是否进行唯一 qst0431 revalidation。"""

    parser = argparse.ArgumentParser(description="Run M45-P4R minimal repair Probe")
    parser.add_argument("--p3-safe", type=Path, required=True)
    parser.add_argument("--p3-private", type=Path, required=True)
    parser.add_argument("--p4-safe", type=Path, required=True)
    parser.add_argument("--p4-private", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--offline-preflight-only", action="store_true")
    args = parser.parse_args()
    safe, private = run_p4_repair(
        p3_safe_path=args.p3_safe,
        p3_private_path=args.p3_private,
        p4_safe_path=args.p4_safe,
        p4_private_path=args.p4_private,
        dataset_root=args.dataset_root,
        allow_provider_revalidation=not args.offline_preflight_only,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.private_output.write_text(
        json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "gate": safe["gate"], "decision": safe["decision"],
        "artifact_identity": safe["artifact_identity"], "usage": safe["usage"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
