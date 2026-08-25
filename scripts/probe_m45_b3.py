"""M45 B3 预注册 Live Dev Probe runner。

P1/P2/P3 输出都是 exploratory/baseline-ineligible 的安全诊断证据，不登记正式 Eval 基线。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from engine.governance import authorize_document, test_caller
from engine.phase4b.contracts import load_b0_contract_bundle
from engine.phase4b.identity import canonical_hash
from engine.phase4b.loop_contracts import EvidenceDelta, ProgressDecision, ResourceConsumption
from engine.phase4b.rag_diagnostics import (
    RAGRecoveryDiagnostic,
    RecoveryExecution,
    RecoveryObservation,
    RequirementSlot,
)
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.rag.enterprise_product_runtime import EnterpriseProductRuntimeConfig, load_enterprise_product_runtime
from engine.rag.evidence import (
    DocumentContextCoordinates,
    DocumentEvidencePayload,
    Evidence,
    EvidenceLedger,
    make_document_evidence,
)
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool, RetrievalDiagnostics, RetrievalOutcome
from eval.rag_action_diagnostics import load_diagnostic_campaign


def _business_t4_slots() -> tuple[RequirementSlot, ...]:
    """从 B0 的 policy_scope/materials/conditions typed requirement 冻结三类语义槽。

    marker 是规则语义，不是 document key/title。focused query 也只描述业务要求，因此即使
    active release 内文档改名，rewrite 仍通过检索与 ACL seam 工作，而不是命中硬编码 ID。
    """

    return (
        RequirementSlot(
            "policy_scope",
            "退款政策适用范围、支持的退款原因与基础总则",
            (("7 天无理由", "七天无理由"), ("物流损坏",), ("价保补差",)),
        ),
        RequirementSlot(
            "required_materials",
            "质量问题退款需要哪些申请材料和补充证据",
            (("订单号",), ("照片",), ("视频",)),
        ),
        RequirementSlot(
            "processing_conditions",
            "质量问题全额退款的确认前提和处理路径",
            (("质检确认",), ("原支付路径",), ("全额退款",)),
        ),
    )


def run_p1() -> dict[str, Any]:
    """执行 business T4 initial + deterministic focused rewrite，零模型/Composer。"""

    campaign = load_diagnostic_campaign()
    b0 = load_b0_contract_bundle()
    t4 = b0.scenario("T4")
    question = str(t4["turns"][0]["question"])
    caller = test_caller(
        caller_id="m45-p1-fixture",
        roles=("ops", "customer_service"),
        tenant_id="phase4b-demo-tenant",
    )
    run_id = f"m45-p1-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    request = KnowledgeRequest(
        question=question,
        caller=caller,
        purpose="answer_evidence",
        run_id=run_id,
    )
    diagnostic = RAGRecoveryDiagnostic()
    tool = KnowledgeTool()
    slots = _business_t4_slots()
    observation = diagnostic.observe(
        scenario_id="T4",
        runtime_scope="business_release",
        slots=slots,
        tool=tool,
        request=request,
    )
    execution = diagnostic.execute(
        observation=observation,
        slots=slots,
        tool=tool,
        request=request,
    )

    def document_keys(evidence: tuple[Any, ...]) -> set[str]:
        return {
            item.payload.document_key
            for item in evidence
            if isinstance(item.payload, DocumentEvidencePayload)
        }

    initial_keys = document_keys(observation.initial_outcome.selected_evidence)
    added_keys = document_keys(execution.added_evidence)
    # gold/document keys 只在动作完成后用于本地 oracle；不会进入 runtime slot/query 或安全投影。
    assertions = {
        "initial_quality_present": "refund_policy_quality" in initial_keys,
        "initial_basic_missing": "refund_policy_basic" not in initial_keys,
        "rewrite_eligible": observation.eligible_actions == ("query_rewrite_candidate", "stop"),
        "wrong_expansion_rejected": "context_expansion_candidate" in observation.rejected_actions,
        "basic_evidence_added": "refund_policy_basic" in added_keys,
        "quality_evidence_retained": "refund_policy_quality" in initial_keys,
        "evidence_gain": execution.evidence_delta.gained,
        "budget_respected": execution.consumed.retrieval_batches <= 2,
        "zero_model_and_tokens": execution.consumed.model_calls == execution.consumed.total_tokens == 0,
    }
    passed = all(assertions.values())
    payload: dict[str, Any] = {
        "schema_version": "phase4b-m45-live-probe-v1",
        "probe_id": "M45-P1",
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "scenario_id": "T4",
        "execution": execution.safe_projection(),
        "assertions": assertions,
        "gate": "passed" if passed else "failed",
        "decision": "continue" if passed else "revise",
        "usage": {
            "retrieval_calls": observation.initial_outcome.diagnostics.adapter_calls + execution.consumed.retrieval_batches,
            "embedding_provider_attempts": 0,
            "chat_model_calls": 0,
            "composer_calls": 0,
            "observed_chat_tokens": 0,
            "token_usage_observed": True,
        },
        "runtime_identity": {
            "release_identity": observation.initial_outcome.diagnostics.release_identity,
            "corpus_identity": observation.initial_outcome.diagnostics.corpus_identity,
            "retrieval_adapter_identity": observation.initial_outcome.diagnostics.adapter_identity,
            "retrieval_recipe_identity": observation.initial_outcome.diagnostics.recipe_identity,
        },
        "reserve_access_state": "sealed",
    }
    payload["artifact_identity"] = canonical_hash(payload)
    return payload


_EXTERNAL_QUESTIONS = {
    "qst_0420": "For EXP-002 (eu-west→us-east), what egress cost rate and measurement basis does the cost penalty catalog use?",
    "qst_0431": "What is the procedure for an emergency rollback of a Serving Runtime release (Hosted and Dedicated)?",
    "qst_0461": "What is the proposed weekly cleanup schedule and routine for tidying the engineering kitchen fridge so old opened items get discarded?",
}


def _external_slots(scenario_id: str) -> tuple[RequirementSlot, ...]:
    """预检索冻结的 typed slot；不包含 gold 文档 ID、标题或运行后人工 verdict。"""

    recipes = {
        "qst_0420": (
            RequirementSlot(
                "current_egress_rate",
                "EXP-002 eu-west us-east current authoritative egress cost rate cost penalty catalog",
                (
                    ("exp-002",),
                    ("egress",),
                    ("rate", "cost"),
                    ("current", "updated", "approved", "effective", "authoritative"),
                ),
            ),
            RequirementSlot(
                "measurement_basis",
                "EXP-002 eu-west us-east current authoritative egress measurement basis cost penalty catalog",
                (
                    ("exp-002",),
                    ("egress",),
                    ("measurement", "basis", "billing"),
                    ("current", "updated", "approved", "effective", "authoritative"),
                ),
            ),
        ),
        "qst_0431": (
            RequirementSlot(
                "rollback_core",
                "Serving Runtime emergency rollback procedure core steps",
                (("serving runtime",), ("emergency",), ("rollback",)),
            ),
            RequirementSlot(
                "hosted_completion",
                "Serving Runtime emergency rollback procedure Hosted environment",
                (("hosted",), ("rollback",)),
            ),
            RequirementSlot(
                "dedicated_completion",
                "Serving Runtime emergency rollback procedure Dedicated environment",
                (("dedicated",), ("rollback",)),
            ),
        ),
        "qst_0461": (
            RequirementSlot(
                "opened_items",
                "engineering kitchen fridge cleanup routine old opened items",
                (("opened",), ("item", "food", "jar")),
            ),
            RequirementSlot(
                "old_item_discard",
                "engineering kitchen fridge cleanup routine discard old opened items",
                (("old",), ("opened",), ("discard", "remove", "toss")),
            ),
            RequirementSlot(
                "weekly_schedule",
                "engineering kitchen fridge proposed weekly cleanup schedule and routine",
                (("weekly",), ("schedule", "routine"), ("cleanup", "tidy")),
            ),
        ),
    }
    try:
        return recipes[scenario_id]
    except KeyError as exc:
        raise ValueError("unknown_m45_external_scenario") from exc


def _expected_docs_after_action(dataset_root: Path, scenario_id: str) -> set[str]:
    """动作完成后才读取 gold，仅用于离线 oracle，不返回给 runtime。"""

    for line in (dataset_root / "raw" / "questions.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item.get("question_id") == scenario_id:
            return {str(value) for value in item.get("expected_doc_ids") or ()}
    raise ValueError("m45_external_scenario_missing")


def _private_execution_projection(
    *, scenario_id: str, question: str, slots: tuple[RequirementSlot, ...], execution: Any,
) -> dict[str, Any]:
    """只允许写入 external diagnostic store 的完整复核视图。"""

    def evidence_view(item: Any) -> dict[str, Any]:
        payload = item.payload
        coordinates = payload.context_coordinates if isinstance(payload, DocumentEvidencePayload) else None
        return {
            "ref": item.ref.audit_projection(),
            "document_key": payload.document_key if isinstance(payload, DocumentEvidencePayload) else None,
            "title": payload.title if isinstance(payload, DocumentEvidencePayload) else None,
            "content": payload.content if isinstance(payload, DocumentEvidencePayload) else None,
            "coordinates": dict(coordinates.__dict__) if coordinates is not None else None,
        }

    return {
        "scenario_id": scenario_id,
        "question": question,
        "slots": [{
            "identity": slot.identity,
            "focused_query": slot.focused_query,
            "support_marker_groups": [list(group) for group in slot.support_marker_groups],
            "signature": slot.signature,
        } for slot in slots],
        "initial_evidence": [evidence_view(item) for item in execution.observation.initial_outcome.selected_evidence],
        "added_evidence": [evidence_view(item) for item in execution.added_evidence],
        "safe_execution": execution.safe_projection(),
    }


def _run_external_scenario(*, scenario_id: str, product: Any, dataset_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """同一 semantic product runtime 上运行一次 initial + 唯一 recovery action。"""

    question = _EXTERNAL_QUESTIONS[scenario_id]
    slots = _external_slots(scenario_id)
    caller = test_caller(caller_id=f"m45-{scenario_id}", roles=("demo_user",))
    request = KnowledgeRequest(
        question=question,
        caller=caller,
        purpose="answer_evidence",
        run_id=f"m45-{scenario_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    )
    adapter = EnterpriseSiblingExpansionAdapter(product.runtime)
    diagnostic = RAGRecoveryDiagnostic()
    tool = product.runtime.knowledge_tool()
    observation = diagnostic.observe(
        scenario_id=scenario_id, runtime_scope="external_profile", slots=slots,
        tool=tool, request=request, expansion_adapter=adapter,
    )
    expected_action = load_diagnostic_campaign().by_id()[scenario_id].expected_action
    if expected_action in observation.eligible_actions:
        execution = diagnostic.execute(
            observation=observation, slots=slots, tool=tool, request=request,
            expansion_adapter=adapter,
        )
    else:
        # ★ Probe 只验证预注册 action；若 trigger 不成立就停，绝不能偷偷执行另一动作，
        # 否则 P3 expansion failure 会额外发送 rewrite query 并突破 provider 硬预算。
        execution = RecoveryExecution(
            observation=observation,
            chosen_action="stop",
            status="blocked",
            evidence_delta=EvidenceDelta(),
            consumed=ResourceConsumption(actions=1, token_usage_observed=True),
            progress=ProgressDecision(False, False, "expected_action_not_eligible"),
            duplicate_key=canonical_hash({
                "scenario_id": scenario_id,
                "expected_action": expected_action,
                "requirement_signature": observation.requirement_signature,
            }),
            termination_reason="expected_action_not_eligible",
            elapsed_ms=0.0,
        )
    expected_docs = _expected_docs_after_action(dataset_root, scenario_id)
    added_logical = {
        item.payload.context_coordinates.logical_document_id
        for item in execution.added_evidence
        if isinstance(item.payload, DocumentEvidencePayload) and item.payload.context_coordinates is not None
    }
    unsupported = tuple(slot for slot in slots if slot.identity in observation.unsupported_slot_identities)
    wrong = "context_expansion_candidate" if expected_action == "query_rewrite_candidate" else "query_rewrite_candidate"
    assertions = {
        "expected_action_selected": execution.chosen_action == expected_action,
        "wrong_action_rejected": wrong in observation.rejected_actions,
        "stop_available": "stop" in observation.eligible_actions,
        "evidence_gain": execution.evidence_delta.gained,
        "added_evidence_current_authority": all(
            item.ref.authority_identity.startswith("enterprise-rag-bench/") for item in execution.added_evidence
        ),
        "added_evidence_supports_gap": bool(unsupported) and all(
            slot.supported_by(observation.initial_outcome.selected_evidence + execution.added_evidence)
            for slot in unsupported
        ),
        "offline_gold_overlap": bool(added_logical & expected_docs),
        "budget_respected": execution.consumed.retrieval_batches <= 2,
        "zero_chat_model_and_tokens": execution.consumed.model_calls == execution.consumed.total_tokens == 0,
    }
    if expected_action == "context_expansion_candidate":
        assertions["offline_gold_overlap"] = bool(added_logical) and added_logical <= expected_docs
        assertions["zero_extra_embedding"] = execution.consumed.retrieval_batches == 0
    passed = all(assertions.values())
    safe = {
        "scenario_id": scenario_id,
        "execution": execution.safe_projection(),
        "assertions": assertions,
        "gate": "passed" if passed else "failed",
        "decision": "continue" if passed else "revise",
        "usage": {
            "retrieval_calls": observation.initial_outcome.diagnostics.adapter_calls + execution.consumed.retrieval_batches,
            "embedding_provider_attempts": observation.initial_outcome.diagnostics.adapter_calls + execution.consumed.retrieval_batches,
            "chat_model_calls": 0,
            "composer_calls": 0,
            "observed_chat_tokens": 0,
            "token_usage_observed": True,
        },
        "runtime_identity": product.identity.safe_projection(),
    }
    return safe, _private_execution_projection(
        scenario_id=scenario_id, question=question, slots=slots, execution=execution,
    )


def _verified_json_artifact(path: Path) -> dict[str, Any]:
    """读取 immutable Probe artifact 并复算其 canonical identity。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    observed = payload.get("artifact_identity")
    unsigned = dict(payload)
    unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise ValueError("m45_source_artifact_identity_mismatch")
    return payload


def _rehydrate_evidence_views(
    *, product: Any, views: list[dict[str, Any]], caller: Any, purpose: str, run_id: str,
) -> tuple[Evidence, ...]:
    """只信 immutable coordinates/ref identity，正文始终回当前 SQLite authority 读取。"""

    entries = {entry.document_key: entry for entry in product.runtime.bundle.entries}
    evidence: list[Evidence] = []
    for view in views:
        coordinates = DocumentContextCoordinates(**view["coordinates"])
        document_key = f"enterprise-unit:{coordinates.unit_identity}"
        entry = entries.get(document_key)
        if entry is None:
            raise ValueError("m45_continuation_unit_missing")
        pre_selection = authorize_document(
            caller=caller, entry=entry, purpose=purpose, phase="pre_selection",
        )
        pre_generation = authorize_document(
            caller=caller, entry=entry, purpose=purpose, phase="pre_generation",
        )
        if not pre_selection.allowed or not pre_generation.allowed:
            raise ValueError("m45_continuation_seed_acl_denied")
        materialized = product.runtime.context_loader(entry)
        if materialized.coordinates != coordinates:
            raise ValueError("m45_continuation_coordinates_drift")
        source_ref = view["ref"]
        if (
            materialized.entry.revision != source_ref["revision"]
            or materialized.entry.content_identity != source_ref["content_identity"]
            or materialized.entry.anchor != source_ref["anchor"]
        ):
            raise ValueError("m45_continuation_evidence_identity_drift")
        evidence.append(make_document_evidence(
            run_id=run_id,
            release_identity=product.runtime.bundle.release_identity,
            entry=materialized.entry,
            purpose=purpose,
            authorization=pre_selection,
            runtime_ref="m45:p2d:rehydrated-authority",
            context_coordinates=coordinates,
        ))
    return tuple(evidence)


def run_p2_continuation(
    *, probe_id: str, source_safe_path: Path, source_private_path: Path, dataset_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """复用 P2 Round 2 Evidence 做零 embedding sibling-v2 continuation expansion。"""

    if probe_id != "M45-P2D":
        raise ValueError("m45_continuation_probe_invalid")

    source_safe = _verified_json_artifact(source_safe_path)
    source_private = _verified_json_artifact(source_private_path)
    if (
        source_safe.get("probe_id") != "M45-P2"
        or source_private.get("probe_id") != "M45-P2"
        or source_private.get("safe_artifact_identity") != source_safe.get("artifact_identity")
        or len(source_safe.get("scenarios") or ()) != 1
        or len(source_private.get("scenarios") or ()) != 1
    ):
        raise ValueError("m45_p2c_source_lineage_invalid")
    source_safe_scenario = source_safe["scenarios"][0]
    source_private_scenario = source_private["scenarios"][0]
    if (
        source_safe_scenario.get("scenario_id") != "qst_0420"
        or source_private_scenario.get("scenario_id") != "qst_0420"
        or source_private_scenario.get("safe_execution") != source_safe_scenario.get("execution")
    ):
        raise ValueError("m45_p2c_source_execution_mismatch")

    config = EnterpriseProductRuntimeConfig.from_settings(get_settings(), allow_cross_thread=False)
    caller = test_caller(caller_id="m45-qst_0420-p2c", roles=("demo_user",))
    purpose = "answer_evidence"
    run_id = f"m45-qst_0420-p2d-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    request = KnowledgeRequest(
        question=_EXTERNAL_QUESTIONS["qst_0420"], caller=caller, purpose=purpose, run_id=run_id,
    )
    slots = _external_slots("qst_0420")
    source_execution = source_safe_scenario["execution"]
    source_observation = source_execution["observation"]
    with load_enterprise_product_runtime(config=config) as product:
        initial = _rehydrate_evidence_views(
            product=product, views=source_private_scenario["initial_evidence"],
            caller=caller, purpose=purpose, run_id=run_id,
        )
        added = _rehydrate_evidence_views(
            product=product, views=source_private_scenario["added_evidence"],
            caller=caller, purpose=purpose, run_id=run_id,
        )
        ledger = EvidenceLedger.from_candidates(run_id=run_id, evidence=initial)
        ledger = ledger.transition(
            evidence_ids=tuple(item.ref.evidence_id for item in initial), to_stage="selected"
        )
        runtime_identity = product.identity.safe_projection()
        initial_outcome = RetrievalOutcome(
            execution_outcome="completed",
            reason_code="immutable_probe_rehydrated",
            selected_evidence=initial,
            ledger=ledger,
            pre_generation_authorizations=(),
            diagnostics=RetrievalDiagnostics(
                run_ref=f"source:{source_safe['artifact_identity'][:20]}",
                query_fingerprint=source_observation["initial_outcome"]["diagnostics"]["query_fingerprint"],
                release_identity=runtime_identity["release_identity"],
                corpus_identity=runtime_identity["corpus_identity"],
                adapter_identity=runtime_identity["retrieval_adapter_identity"],
                recipe_identity=runtime_identity["retrieval_recipe_identity"],
                adapter_calls=0,
                authorized_entry_count=len(initial),
                candidate_count=len(initial),
                selected_count=len(initial),
                elapsed_ms=0.0,
            ),
        )
        prior_observation = RecoveryObservation(
            scenario_id="qst_0420",
            runtime_scope="external_profile",
            requirement_signature=source_observation["requirement_signature"],
            initial_outcome=initial_outcome,
            unsupported_slot_identities=tuple(source_observation["unsupported_slot_identities"]),
            eligible_actions=tuple(source_observation["eligible_actions"]),
            rejected_actions=tuple(source_observation["rejected_actions"]),
        )
        prior = RecoveryExecution(
            observation=prior_observation,
            chosen_action="query_rewrite_candidate",
            status="completed",
            evidence_delta=EvidenceDelta(added=tuple(item.ref.audit_projection() for item in added)),
            consumed=ResourceConsumption(**source_execution["consumed"]),
            progress=ProgressDecision(**source_execution["progress"]),
            duplicate_key=source_execution["duplicate_key"],
            termination_reason=source_execution["termination_reason"],
            elapsed_ms=float(source_execution["elapsed_ms"]),
            added_evidence=added,
        )
        adapter = EnterpriseSiblingExpansionAdapter(product.runtime)
        diagnostic = RAGRecoveryDiagnostic()
        observation = diagnostic.observe_after_rewrite(
            prior=prior, slots=slots, expansion_adapter=adapter, request=request,
        )
        execution = diagnostic.execute(
            observation=observation, slots=slots, tool=product.runtime.knowledge_tool(),
            request=request, expansion_adapter=adapter,
        )
        expected_docs = _expected_docs_after_action(dataset_root, "qst_0420")
        added_logical = {
            item.payload.context_coordinates.logical_document_id
            for item in execution.added_evidence
            if isinstance(item.payload, DocumentEvidencePayload) and item.payload.context_coordinates is not None
        }
        assertions = {
            "source_identity_verified": True,
            "expansion_selected_after_rewrite": execution.chosen_action == "context_expansion_candidate",
            "rewrite_repetition_rejected": "query_rewrite_candidate" in observation.rejected_actions,
            "stop_available": "stop" in observation.eligible_actions,
            "evidence_gain": execution.evidence_delta.gained,
            "remaining_slots_supported": all(
                slot.supported_by(added + execution.added_evidence) for slot in slots
            ),
            "offline_gold_document_only": bool(added_logical) and added_logical <= expected_docs,
            "zero_embedding_retrieval_model": (
                execution.consumed.retrieval_batches == execution.consumed.model_calls == 0
            ),
            "chain_budget_respected": source_execution["consumed"]["actions"] + execution.consumed.actions == 2,
        }
        passed = all(assertions.values())
        safe: dict[str, Any] = {
            "schema_version": "phase4b-m45-live-probe-v1",
            "probe_id": probe_id,
            "classification": "exploratory",
            "baseline_eligible": False,
            "campaign_identity": load_diagnostic_campaign().identity,
            "source_artifact_identity": source_safe["artifact_identity"],
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "scenario_id": "qst_0420",
            "execution": execution.safe_projection(),
            "assertions": assertions,
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
        private = _private_execution_projection(
            scenario_id="qst_0420", question=_EXTERNAL_QUESTIONS["qst_0420"],
            slots=slots, execution=execution,
        )
    safe["artifact_identity"] = canonical_hash(safe)
    private_payload = {
        "schema_version": "phase4b-m45-private-probe-v1",
        "probe_id": probe_id,
        "safe_artifact_identity": safe["artifact_identity"],
        "source_artifact_identity": source_safe["artifact_identity"],
        "scenario": private,
    }
    private_payload["artifact_identity"] = canonical_hash(private_payload)
    return safe, private_payload


def run_external_probe(*, probe_id: str, dataset_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """P2 单题；P3 两题，共用同一个已验证 semantic runtime。"""

    config = EnterpriseProductRuntimeConfig.from_settings(get_settings(), allow_cross_thread=False)
    scenario_ids = ("qst_0420",) if probe_id == "M45-P2" else ("qst_0431", "qst_0461")
    with load_enterprise_product_runtime(config=config) as product:
        results = tuple(
            _run_external_scenario(scenario_id=item, product=product, dataset_root=dataset_root)
            for item in scenario_ids
        )
    safe_scenarios = [item[0] for item in results]
    private_scenarios = [item[1] for item in results]
    passed = all(item["gate"] == "passed" for item in safe_scenarios)
    safe: dict[str, Any] = {
        "schema_version": "phase4b-m45-live-probe-v1",
        "probe_id": probe_id,
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": load_diagnostic_campaign().identity,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": safe_scenarios,
        "gate": "passed" if passed else "failed",
        "decision": "continue" if passed else "revise",
        "usage": {
            key: sum(int(item["usage"][key]) for item in safe_scenarios)
            for key in ("retrieval_calls", "embedding_provider_attempts", "chat_model_calls", "composer_calls", "observed_chat_tokens")
        },
        "reserve_access_state": "sealed",
    }
    safe["usage"]["token_usage_observed"] = True
    safe["artifact_identity"] = canonical_hash(safe)
    private = {
        "schema_version": "phase4b-m45-private-probe-v1",
        "probe_id": probe_id,
        "safe_artifact_identity": safe["artifact_identity"],
        "scenarios": private_scenarios,
    }
    private["artifact_identity"] = canonical_hash(private)
    return safe, private


def main() -> None:
    """按预注册 Probe ID 执行对应场景并写出 safe/private artifact。"""

    parser = argparse.ArgumentParser(description="Run one preregistered M45 Live Dev Probe")
    parser.add_argument("--probe", required=True, choices=("M45-P1", "M45-P2", "M45-P2D", "M45-P3"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--private-output", type=Path)
    parser.add_argument("--source-safe", type=Path)
    parser.add_argument("--source-private", type=Path)
    args = parser.parse_args()
    private: dict[str, Any] | None = None
    if args.probe == "M45-P1":
        payload = run_p1()
    elif args.probe == "M45-P2D":
        if any(value is None for value in (
            args.dataset_root, args.private_output, args.source_safe, args.source_private,
        )):
            parser.error("P2D requires --dataset-root, --private-output, --source-safe and --source-private")
        assert args.dataset_root is not None and args.source_safe is not None and args.source_private is not None
        payload, private = run_p2_continuation(
            probe_id=args.probe,
            source_safe_path=args.source_safe,
            source_private_path=args.source_private,
            dataset_root=args.dataset_root,
        )
    else:
        if args.dataset_root is None or args.private_output is None:
            parser.error("P2/P3 require --dataset-root and --private-output")
        payload, private = run_external_probe(probe_id=args.probe, dataset_root=args.dataset_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if private is not None:
        assert args.private_output is not None
        args.private_output.parent.mkdir(parents=True, exist_ok=True)
        args.private_output.write_text(json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "probe_id": payload["probe_id"],
        "gate": payload["gate"],
        "decision": payload["decision"],
        "artifact_identity": payload["artifact_identity"],
        "usage": payload["usage"],
        "output": str(args.output),
        "private_output": str(args.private_output) if args.private_output is not None else None,
    }, ensure_ascii=False))
    if payload["gate"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
