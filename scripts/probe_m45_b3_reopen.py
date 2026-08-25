"""M45-P4：复用 P3 initial Evidence 的 structured proposal + sibling expansion Probe。

本 runner 不重跑 semantic retrieval。它先核验 P3 safe/private immutable lineage，再回 SQLite
authority 重水化当时 selected Evidence，随后每题只调用一次 Qwen proposal；通过确定性 validator
后才允许既有 sibling-v2 action。完整 prompt/response 只写 external v1.1.0 store。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from engine.governance import test_caller
from engine.nl2sql.generator import LLMGenerationError
from engine.phase4b.identity import canonical_hash
from engine.phase4b.loop_contracts import EvidenceDelta, ProgressDecision, ResourceConsumption
from engine.phase4b.rag_diagnostics import RAGRecoveryDiagnostic, RecoveryExecution
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.phase4b.rag_requirement_proposal import (
    EvidenceAwareRequirementProposer,
    RequirementProposalError,
    make_qwen_requirement_proposal_client,
)
from engine.rag.enterprise_product_runtime import EnterpriseProductRuntimeConfig, load_enterprise_product_runtime
from engine.rag.evidence import DocumentEvidencePayload, EvidenceLedger
from engine.rag.knowledge_tool import KnowledgeRequest, RetrievalDiagnostics, RetrievalOutcome
from eval.rag_action_diagnostics import load_reopened_diagnostic_campaign
from scripts.probe_m45_b3 import (
    _EXTERNAL_QUESTIONS,
    _expected_docs_after_action,
    _private_execution_projection,
    _rehydrate_evidence_views,
    _verified_json_artifact,
)


def _rehydrated_outcome(
    *, product: Any, scenario_safe: dict[str, Any], scenario_private: dict[str, Any],
    caller: Any, request: KnowledgeRequest,
) -> RetrievalOutcome:
    """P3 coordinates/ref 只作 identity，正文必须回当前 authority 读取并重新授权。"""

    evidence = _rehydrate_evidence_views(
        product=product,
        views=scenario_private["initial_evidence"],
        caller=caller,
        purpose=request.purpose,
        run_id=request.run_id,
    )
    ledger = EvidenceLedger.from_candidates(run_id=request.run_id, evidence=evidence)
    ledger = ledger.transition(
        evidence_ids=tuple(item.ref.evidence_id for item in evidence), to_stage="selected"
    )
    source_diagnostics = scenario_safe["execution"]["observation"]["initial_outcome"]["diagnostics"]
    runtime_identity = product.identity.safe_projection()
    return RetrievalOutcome(
        execution_outcome="completed",
        reason_code="immutable_probe_rehydrated",
        selected_evidence=evidence,
        ledger=ledger,
        pre_generation_authorizations=(),
        diagnostics=RetrievalDiagnostics(
            run_ref=f"source:{canonical_hash(scenario_safe)[:20]}",
            query_fingerprint=source_diagnostics["query_fingerprint"],
            release_identity=runtime_identity["release_identity"],
            corpus_identity=runtime_identity["corpus_identity"],
            adapter_identity=runtime_identity["retrieval_adapter_identity"],
            recipe_identity=runtime_identity["retrieval_recipe_identity"],
            adapter_calls=0,
            authorized_entry_count=len(evidence),
            candidate_count=len(evidence),
            selected_count=len(evidence),
            elapsed_ms=0.0,
        ),
    )


def _blocked_execution(*, scenario_id: str, reason: str) -> dict[str, Any]:
    """proposal 失败时没有合法 Observation；安全 artifact 显式记录未执行。"""

    return {
        "scenario_id": scenario_id,
        "chosen_action": "stop",
        "status": "blocked",
        "termination_reason": reason,
        "evidence_delta": EvidenceDelta().safe_projection(),
        "consumed": ResourceConsumption(
            actions=0, token_usage_observed=True,
        ).safe_projection(),
        "progress": ProgressDecision(False, False, reason).safe_projection(),
    }


def run_p4(
    *, source_safe_path: Path, source_private_path: Path, dataset_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """两题各一次 proposal；不重跑 P3 initial，不允许 fallback/retry。"""

    campaign = load_reopened_diagnostic_campaign()
    source_safe = _verified_json_artifact(source_safe_path)
    source_private = _verified_json_artifact(source_private_path)
    if (
        source_safe.get("probe_id") != "M45-P3"
        or source_private.get("probe_id") != "M45-P3"
        or source_private.get("safe_artifact_identity") != source_safe.get("artifact_identity")
        or source_safe.get("campaign_identity") != campaign.predecessor_campaign_identity
    ):
        raise ValueError("m45_p4_source_lineage_invalid")
    safe_by_id = {item["scenario_id"]: item for item in source_safe.get("scenarios") or ()}
    private_by_id = {item["scenario_id"]: item for item in source_private.get("scenarios") or ()}
    if set(safe_by_id) != {"qst_0431", "qst_0461"} or set(private_by_id) != set(safe_by_id):
        raise ValueError("m45_p4_source_scenario_set_invalid")
    for scenario_id in safe_by_id:
        if private_by_id[scenario_id].get("safe_execution") != safe_by_id[scenario_id].get("execution"):
            raise ValueError("m45_p4_source_execution_mismatch")

    settings = get_settings()
    client = make_qwen_requirement_proposal_client(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        model="qwen3.7-plus",
        timeout=settings.llm_timeout_seconds,
    )
    proposer = EvidenceAwareRequirementProposer(client)
    config = EnterpriseProductRuntimeConfig.from_settings(settings, allow_cross_thread=False)
    safe_scenarios: list[dict[str, Any]] = []
    private_scenarios: list[dict[str, Any]] = []
    with load_enterprise_product_runtime(config=config) as product:
        adapter = EnterpriseSiblingExpansionAdapter(product.runtime)
        tool = product.runtime.knowledge_tool()
        diagnostic = RAGRecoveryDiagnostic()
        runtime_identity = product.identity.safe_projection()
        for scenario_id in ("qst_0431", "qst_0461"):
            caller = test_caller(caller_id=f"m45-p4-{scenario_id}", roles=("demo_user",))
            request = KnowledgeRequest(
                question=_EXTERNAL_QUESTIONS[scenario_id],
                caller=caller,
                purpose="answer_evidence",
                run_id=f"m45-p4-{scenario_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            )
            initial = _rehydrated_outcome(
                product=product,
                scenario_safe=safe_by_id[scenario_id],
                scenario_private=private_by_id[scenario_id],
                caller=caller,
                request=request,
            )
            before_calls, before_tokens = client.request_count, client.total_tokens
            try:
                proposal = proposer.propose(
                    question=request.question,
                    current_evidence=initial.selected_evidence,
                )
            except (LLMGenerationError, RequirementProposalError) as exc:
                calls = client.request_count - before_calls
                tokens = client.total_tokens - before_tokens
                reason = getattr(exc, "reason_code", None) or getattr(exc, "error_subtype", None) or "proposal_failed"
                safe_scenarios.append({
                    "scenario_id": scenario_id,
                    "proposal_status": "failed",
                    "proposal_error": str(reason),
                    "execution": _blocked_execution(scenario_id=scenario_id, reason=str(reason)),
                    "assertions": {"proposal_valid": False, "expected_action_selected": False},
                    "gate": "failed",
                    "decision": "stop",
                    "usage": {
                        "retrieval_calls": 0,
                        "embedding_provider_attempts": 0,
                        "chat_model_calls": calls,
                        "composer_calls": 0,
                        "observed_chat_tokens": tokens,
                        "token_usage_observed": True,
                    },
                    "runtime_identity": runtime_identity,
                })
                private_scenarios.append({
                    "scenario_id": scenario_id,
                    "question": request.question,
                    "proposal_error": str(reason),
                    "proposal_failure": {
                        "prompt": getattr(exc, "prompt", ""),
                        "raw_response": getattr(exc, "raw_response", ""),
                        "usage": (
                            getattr(exc, "usage", None).safe_projection()
                            if getattr(exc, "usage", None) is not None else None
                        ),
                    },
                    "source_initial_evidence": private_by_id[scenario_id]["initial_evidence"],
                })
                continue

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
                execution = RecoveryExecution(
                    observation=observation,
                    chosen_action="stop",
                    status="blocked",
                    evidence_delta=EvidenceDelta(),
                    consumed=ResourceConsumption(actions=1, token_usage_observed=True),
                    progress=ProgressDecision(False, False, "expected_action_not_eligible"),
                    duplicate_key=canonical_hash({
                        "scenario_id": scenario_id,
                        "campaign_identity": campaign.identity,
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
                "proposal_one_call": proposal.usage.calls == 1,
                "proposal_has_unsupported_slots": bool(proposal.slots),
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
            safe_scenarios.append({
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
            })
            private_execution = _private_execution_projection(
                scenario_id=scenario_id,
                question=request.question,
                slots=proposal.slots,
                execution=execution,
            )
            private_execution["proposal"] = proposal.private_projection()
            private_execution["source_artifact_identity"] = source_safe["artifact_identity"]
            private_scenarios.append(private_execution)

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
        "schema_version": "phase4b-m45-live-probe-v2",
        "probe_id": "M45-P4",
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "predecessor_campaign_identity": campaign.predecessor_campaign_identity,
        "source_artifact_identity": source_safe["artifact_identity"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": safe_scenarios,
        "gate": "passed" if passed else "failed",
        "decision": "continue" if passed else "stop",
        "usage": usage,
        "budget_respected": budget_ok,
        "reserve_access_state": "sealed",
    }
    safe["artifact_identity"] = canonical_hash(safe)
    private: dict[str, Any] = {
        "schema_version": "phase4b-m45-private-probe-v2",
        "probe_id": "M45-P4",
        "safe_artifact_identity": safe["artifact_identity"],
        "source_artifact_identity": source_safe["artifact_identity"],
        "campaign_identity": campaign.identity,
        "scenarios": private_scenarios,
    }
    private["artifact_identity"] = canonical_hash(private)
    return safe, private


def main() -> None:
    """执行两题受控 structured proposal P4，并分离写出 safe/private 证据。"""

    parser = argparse.ArgumentParser(description="Run M45-P4 structured proposal Probe")
    parser.add_argument("--source-safe", type=Path, required=True)
    parser.add_argument("--source-private", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    safe, private = run_p4(
        source_safe_path=args.source_safe,
        source_private_path=args.source_private,
        dataset_root=args.dataset_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.private_output.write_text(
        json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "gate": safe["gate"],
        "decision": safe["decision"],
        "artifact_identity": safe["artifact_identity"],
        "usage": safe["usage"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
