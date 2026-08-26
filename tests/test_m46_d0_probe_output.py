"""M46-P0 runner 的安全摘要与“零 recovery execution”硬断言。"""

from __future__ import annotations

from engine.governance import demo_caller
from engine.phase4b.external_requirement_formation import (
    FormedRequirement,
    RequirementFormationResult,
)
from engine.phase4b.rag_diagnostics import RecoveryObservation, RequirementSlot
from engine.rag.evidence_acquisition import AcquisitionResult
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool
from scripts.probe_m46_d0_requirement_formation import _safe_payload


def test_p0_safe_payload_omits_question_slot_identity_and_document_content() -> None:
    """Probe 只保存 hash/枚举/usage/action facts，不执行或泄露私有 formation 输入。"""

    caller = demo_caller(caller_id="m46-p0-safe", roles=("ops", "customer_service"))
    outcome = KnowledgeTool().retrieve(KnowledgeRequest(
        question="质量问题退款需要哪些材料？",
        caller=caller,
        purpose="answer_evidence",
        run_id="m46-p0-safe",
    ))
    initial = AcquisitionResult(outcome=outcome, evidence_validity={}, strategy_identity="fixture")
    slot = RequirementSlot(
        "private_semantic_identity",
        "EXP-002 private focused query",
        (("private marker",),),
        marker_match_mode="token_overlap",
    )
    formation = RequirementFormationResult(
        requirements=(FormedRequirement(
            slot=slot,
            supplier_identity="phase4b-b4-question-obligation-supplier-v1",
            formation_reason_category="requested_fact",
            allowed_recovery_actions=("query_rewrite_candidate",),
        ),),
        decision="structured_question_obligations",
        reason_code="eligible",
        prompt_fingerprint="prompt-hash",
        response_fingerprint="response-hash",
    )
    observation = RecoveryObservation(
        scenario_id="M46-P0",
        runtime_scope="external_profile",
        requirement_signature="requirement-hash",
        initial_outcome=outcome,
        unsupported_slot_identities=("private_semantic_identity",),
        eligible_actions=("query_rewrite_candidate", "stop"),
        rejected_actions=("context_expansion_candidate",),
    )
    payload = _safe_payload(
        scenario_id="qst_0420",
        initial=initial,
        formation=formation,
        observation=observation,
        runtime_identity={"adapter": "fixture"},
    )
    serialized = str(payload).casefold()

    assert payload["recovery_action_executions"] == 0
    assert payload["observation"]["eligible_actions"] == ["query_rewrite_candidate", "stop"]
    assert "slot_signature" in serialized
    assert "private_semantic_identity" not in serialized
    assert "private focused query" not in serialized
    assert "private marker" not in serialized
    assert "质量问题" not in serialized
