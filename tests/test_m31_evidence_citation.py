"""M31 typed Evidence、阶段账本与 citation 篡改反例。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.governance import authorize_document, test_caller as make_test_caller
from engine.rag.catalog import CatalogEntry
from engine.rag.evidence import (
    CitationDraft,
    EvidenceContractError,
    EvidenceLedger,
    allocate_citation_slot,
    make_document_evidence,
    make_sql_evidence,
    validate_citations,
)


def _entry(*, revision: str = "1", status: str = "active", anchor: str = "refund-window") -> CatalogEntry:
    return CatalogEntry(
        document_key="refund-policy", revision=revision, authority_ref="kb/refund.md#refund-window",
        source_kind="policy_markdown", source_key="refund.md", title="退款时限", knowledge_type="policy",
        status=status, anchor=anchor, data_class="role_restricted_policy_text",
        purposes=("answer_evidence",), public=False, allowed_roles=frozenset({"customer_service"}),
        content="签收后七天内可申请退款。", content_identity=f"content-{revision}",
    )


def _document_fixture():
    caller = make_test_caller(caller_id="cs-1", roles={"customer_service"})
    entry = _entry()
    selected_auth = authorize_document(
        caller=caller, entry=entry, purpose="answer_evidence", phase="pre_selection"
    )
    generation_auth = authorize_document(
        caller=caller, entry=entry, purpose="answer_evidence", phase="pre_generation"
    )
    evidence = make_document_evidence(
        run_id="run-1", release_identity="release-1", entry=entry, purpose="answer_evidence",
        authorization=selected_auth, runtime_ref="runtime-1",
    )
    ledger = EvidenceLedger.from_candidates(run_id="run-1", evidence=(evidence,))
    return entry, evidence, generation_auth, ledger


def test_document_evidence_requires_authorization_and_safe_projection_omits_content() -> None:
    entry, evidence, _, ledger = _document_fixture()
    projection = ledger.safe_projection()
    assert evidence.ref.anchor == entry.anchor
    assert "签收后七天" not in str(projection)
    assert "退款时限" not in str(projection)

    denied = authorize_document(
        caller=make_test_caller(caller_id="ops-1", roles={"ops"}),
        entry=entry, purpose="answer_evidence", phase="pre_selection",
    )
    with pytest.raises(EvidenceContractError, match="evidence_unauthorized"):
        make_document_evidence(
            run_id="run-1", release_identity="release-1", entry=entry, purpose="answer_evidence",
            authorization=denied, runtime_ref="runtime-1",
        )


def test_ledger_only_allows_forward_same_run_transitions_and_rechecks_acl_before_generation() -> None:
    _, evidence, generation_auth, ledger = _document_fixture()
    selected = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected")
    visible = selected.transition(
        evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible",
        generation_authorizations={evidence.ref.evidence_id: generation_auth},
    )
    assert visible.stage_of(evidence.ref.evidence_id) == "generation_visible"
    with pytest.raises(EvidenceContractError, match="evidence_transition_invalid"):
        ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible")
    with pytest.raises(EvidenceContractError, match="evidence_unauthorized"):
        selected.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible")
    with pytest.raises(EvidenceContractError, match="evidence_run_mismatch"):
        EvidenceLedger.from_candidates(run_id="other-run", evidence=(evidence,))


def test_sql_evidence_is_typed_and_rejects_non_readonly_input() -> None:
    evidence = make_sql_evidence(
        run_id="sql-run", guarded_sql="SELECT id FROM orders", columns=("id",), rows_count=1,
        result_fingerprint="result-hash", queried_at="2026-08-13T00:00:00Z",
        database_identity="sqlite-seed", runtime_identity="runtime-1", safe_result_view=((1,),),
    )
    assert evidence.ref.evidence_kind == "sql"
    assert "safe_result_view" not in str(evidence.safe_projection())
    with pytest.raises(EvidenceContractError, match="sql_evidence_invalid"):
        make_sql_evidence(
            run_id="sql-run", guarded_sql="DELETE FROM orders", columns=(), rows_count=0,
            result_fingerprint="hash", queried_at="now", database_identity="db", runtime_identity="runtime",
        )


def test_valid_citation_must_reference_same_run_generation_visible_evidence() -> None:
    entry, evidence, generation_auth, ledger = _document_fixture()
    ledger = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected")
    ledger = ledger.transition(
        evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible",
        generation_authorizations={evidence.ref.evidence_id: generation_auth},
    )
    slot = allocate_citation_slot(run_id="run-1", claim_ref="claim-1", ordinal=1)
    draft = CitationDraft("run-1", slot.slot_id, "claim-1", evidence.ref.evidence_id, entry.anchor)
    validated, cited = validate_citations(
        ledger=ledger, slots=(slot,), drafts=(draft,),
        current_entries={(entry.document_key, entry.revision): entry},
        generation_authorizations={evidence.ref.evidence_id: generation_auth},
    )
    assert validated[0].evidence_ref == evidence.ref
    assert cited.stage_of(evidence.ref.evidence_id) == "cited"


def test_multiple_claims_may_reuse_one_generation_visible_evidence() -> None:
    entry, evidence, generation_auth, ledger = _document_fixture()
    ledger = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected")
    ledger = ledger.transition(
        evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible",
        generation_authorizations={evidence.ref.evidence_id: generation_auth},
    )
    slots = (
        allocate_citation_slot(run_id="run-1", claim_ref="claim-1", ordinal=1),
        allocate_citation_slot(run_id="run-1", claim_ref="claim-2", ordinal=1),
    )
    drafts = tuple(
        CitationDraft("run-1", slot.slot_id, slot.claim_ref, evidence.ref.evidence_id, entry.anchor)
        for slot in slots
    )
    validated, cited = validate_citations(
        ledger=ledger, slots=slots, drafts=drafts,
        current_entries={(entry.document_key, entry.revision): entry},
        generation_authorizations={evidence.ref.evidence_id: generation_auth},
    )
    assert len(validated) == 2
    assert cited.stage_of(evidence.ref.evidence_id) == "cited"


def test_authorization_for_another_document_cannot_construct_or_validate_evidence() -> None:
    entry, evidence, generation_auth, ledger = _document_fixture()
    other = replace(entry, document_key="other-policy", anchor="other-anchor")
    caller = make_test_caller(caller_id="cs-1", roles={"customer_service"})
    other_auth = authorize_document(
        caller=caller, entry=other, purpose="answer_evidence", phase="pre_selection"
    )
    with pytest.raises(EvidenceContractError, match="evidence_purpose_invalid"):
        make_document_evidence(
            run_id="run-1", release_identity="release-1", entry=entry, purpose="answer_evidence",
            authorization=other_auth, runtime_ref="runtime-1",
        )

    ledger = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected")
    ledger = ledger.transition(
        evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible",
        generation_authorizations={evidence.ref.evidence_id: generation_auth},
    )
    other_generation_auth = authorize_document(
        caller=caller, entry=other, purpose="answer_evidence", phase="pre_generation"
    )
    slot = allocate_citation_slot(run_id="run-1", claim_ref="claim", ordinal=1)
    draft = CitationDraft("run-1", slot.slot_id, "claim", evidence.ref.evidence_id, entry.anchor)
    with pytest.raises(EvidenceContractError, match="citation_invalid"):
        validate_citations(
            ledger=ledger, slots=(slot,), drafts=(draft,),
            current_entries={(entry.document_key, entry.revision): entry},
            generation_authorizations={evidence.ref.evidence_id: other_generation_auth},
        )


@pytest.mark.parametrize("mutation", ["forged_slot", "wrong_run", "wrong_anchor", "old_revision", "acl_deny"])
def test_citation_tampering_fails_as_single_safe_reason(mutation: str) -> None:
    entry, evidence, generation_auth, ledger = _document_fixture()
    ledger = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected")
    ledger = ledger.transition(
        evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible",
        generation_authorizations={evidence.ref.evidence_id: generation_auth},
    )
    slot = allocate_citation_slot(run_id="run-1", claim_ref="claim-1", ordinal=1)
    draft = CitationDraft("run-1", slot.slot_id, "claim-1", evidence.ref.evidence_id, entry.anchor)
    entries = {(entry.document_key, entry.revision): entry}
    decisions = {evidence.ref.evidence_id: generation_auth}
    if mutation == "forged_slot":
        draft = replace(draft, slot_id="model-made-slot")
    elif mutation == "wrong_run":
        draft = replace(draft, run_id="other-run")
    elif mutation == "wrong_anchor":
        draft = replace(draft, anchor="other-anchor")
    elif mutation == "old_revision":
        entries[(entry.document_key, entry.revision)] = replace(entry, status="revoked")
    else:
        decisions[evidence.ref.evidence_id] = replace(generation_auth, allowed=False, reason_code="role_not_allowed")
    with pytest.raises(EvidenceContractError) as captured:
        validate_citations(
            ledger=ledger, slots=(slot,), drafts=(draft,), current_entries=entries,
            generation_authorizations=decisions,
        )
    assert captured.value.reason_code == "citation_invalid"


def test_candidate_or_selected_only_evidence_cannot_be_cited() -> None:
    entry, evidence, generation_auth, candidate = _document_fixture()
    slot = allocate_citation_slot(run_id="run-1", claim_ref="claim-1", ordinal=1)
    draft = CitationDraft("run-1", slot.slot_id, "claim-1", evidence.ref.evidence_id, entry.anchor)
    for ledger in (
        candidate,
        candidate.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected"),
    ):
        with pytest.raises(EvidenceContractError, match="citation_invalid"):
            validate_citations(
                ledger=ledger, slots=(slot,), drafts=(draft,),
                current_entries={(entry.document_key, entry.revision): entry},
                generation_authorizations={evidence.ref.evidence_id: generation_auth},
            )
