"""M46-A：B4 additive contract 与 reserve 只读边界。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.governance import demo_caller
from engine.phase4b.b4_contracts import B4ContractError, load_b4_contract_bundle
from engine.rag.answer_flow import RAGAnswerFlow, RAGAnswerRequest
from engine.rag.evidence import EvidenceLedger
from engine.rag.evidence_acquisition import AcquisitionResult
from engine.rag.knowledge_tool import RetrievalDiagnostics, RetrievalOutcome


def test_b4_bundle_binds_b2_b3_and_user_confirmed_proposal_boundary() -> None:
    """B4 必须新增身份，而不是把 B2 的单次 retrieval 合同改写成子图。"""

    bundle = load_b4_contract_bundle()
    assert bundle.contract_version == "phase4b-b4-contracts-v1"
    assert bundle.payload["strategies"] == ["pipeline", "subgraph"]
    assert bundle.payload["actions"] == [
        "query_rewrite_candidate", "context_expansion_candidate", "stop",
    ]
    assert bundle.payload["child_budget"]["max_total_retrieval_batches"] == 3
    assert bundle.payload["proposal"] == {
        "enabled_for": "external_profile_only",
        "purpose": "rag_recovery_requirement_proposal",
        "data_class": "public_benchmark_question_with_authorized_evidence",
        "schema_version": "phase4b-b4-question-obligation-proposal-v1",
        "prompt_identity": "phase4b-b4-question-obligation-prompt-v2",
        "outbound_policy_identity": "phase4b-b4-recovery-requirement-proposal-outbound-v1",
        "max_slots": 2,
        "business_outbound": "denied",
    }
    assert bundle.payload["external_requirement_formation"] == {
        "identity": "phase4b-b4-external-requirement-formation-v3",
        "enabled_for": "external_profile_only",
        "precedence": ["procedure_boundary_v1", "structured_question_obligations", "typed_stop"],
        "input_fields": ["question", "authorized_document_evidence", "max_requirements"],
        "max_requirements": 2,
        "question_grounding": "exact_source_spans",
        "qualifier_validation": "server_downgrade_unsupported_current_authority_to_none",
        "value_shape_validation": "server_normalize_to_deterministic_expected_shape",
        "evidence_grounding": "server_question_document_meaningful_token_overlap",
        "answer_value_policy": "question_values_are_constraints_model_values_denied",
        "focused_query_owner": "deterministic_server_assembler",
        "coverage_owner": "deterministic_single_authorized_document_validator",
        "formed_requirement_fields": [
            "slot_signature",
            "supplier_identity",
            "formation_reason_category",
            "allowed_recovery_actions",
            "coverage_semantics",
        ],
    }
    assert bundle.payload["rollout"] == {
        "identity": "phase4b-b4-rollout-decision-v1",
        "decision": "pipeline_default_subgraph_experimental",
        "decision_basis": "historical_no_go_portfolio_lightweight_closure",
        "historical_run_id": "m46-historical-paired-20260826-164511",
        "historical_candidate_identity": "ab66f20dc40eb8a1f1deba3fd16aad466a5a836e7543aacdb65326d182532f78",
        "historical_review": "eval/reports/m46/m46-historical-paired-20260826-164511-review.md",
        "reserve_state": "sealed",
        "reserve_decision_run": "not_run",
        "default_strategy": "pipeline",
        "subgraph_status": "server_controlled_experimental",
        "automatic_cross_strategy_fallback": False,
        "quality_claim": "not_established",
        "reopen_policy": "new_hypothesis_new_candidate_new_authorization",
    }


def test_b4_contract_rejects_tampered_manifest(tmp_path: Path) -> None:
    """候选的参数、预算和 reserve identity 都必须经内容 hash 固定。"""

    # 该断言使用真实文件的 manifest 形状，避免测试在副本里悄悄放宽生产 loader。
    with pytest.raises(B4ContractError, match="b4_contract_identity_mismatch"):
        contract = Path("domain_pack/phase4b/b4_contracts.json")
        bad_manifest = tmp_path / "bad-manifest.json"
        bad_manifest.write_text(
            json.dumps({"contract_version": "phase4b-b4-contracts-v1", "content_identity": "bad"}),
            encoding="utf-8",
        )
        load_b4_contract_bundle(contract, bad_manifest)


def test_answer_flow_only_consumes_document_evidence_acquisition_seam() -> None:
    """替换 acquisition 后，AnswerFlow 仍只消费统一 outcome，不触碰 child strategy 私有状态。"""

    class SentinelAcquirer:
        identity = "m46-sentinel-acquisition"

        def acquire(self, *, request: RAGAnswerRequest, started_at: float) -> AcquisitionResult:
            del started_at
            outcome = RetrievalOutcome(
                execution_outcome="completed",
                reason_code="no_candidate",
                selected_evidence=(),
                ledger=EvidenceLedger.from_candidates(run_id=request.run_id, evidence=()),
                pre_generation_authorizations=(),
                diagnostics=RetrievalDiagnostics(
                    run_ref="run:m46", query_fingerprint="q", release_identity="r", corpus_identity="c",
                    adapter_identity="sentinel", recipe_identity="sentinel", adapter_calls=0,
                    authorized_entry_count=0, candidate_count=0, selected_count=0, elapsed_ms=0.0,
                ),
            )
            return AcquisitionResult(outcome, {"decision": "sentinel"}, self.identity)

    flow = RAGAnswerFlow(evidence_acquirer=SentinelAcquirer())
    outcome, validity = flow._obtain_evidence(  # noqa: SLF001 - seam 的最小直接合同
        RAGAnswerRequest(question="测试", caller=demo_caller(caller_id="m46", roles=("ops",)), run_id="m46"),
        started_at=0.0,
    )
    assert outcome.reason_code == "no_candidate"
    assert validity == {"decision": "sentinel", "acquisition_strategy_identity": "m46-sentinel-acquisition"}
