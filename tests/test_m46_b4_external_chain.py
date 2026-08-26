"""M46-D：external rewrite → expansion → reauthorization 的纯本地纵向链。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

from engine.governance import authorize_document, test_caller as make_test_caller
from engine.phase4b.external_requirement_formation import FormedRequirement
from engine.phase4b.rag_diagnostics import ExpansionPreview, RequirementSlot
from engine.phase4b.rag_subgraph import BoundedRAGSubgraphAcquirer, SlotResolution
from engine.rag.answer_flow import RAGAnswerRequest
from engine.rag.catalog import CatalogEntry
from engine.rag.evidence import Evidence, EvidenceLedger, make_document_evidence
from engine.rag.evidence_acquisition import AcquisitionResult
from engine.rag.knowledge_tool import (
    KnowledgeRequest,
    KnowledgeToolContractError,
    RetrievalDiagnostics,
    RetrievalOutcome,
)


RELEASE = "release-m46-external-fixture"
RUN_ID = "m46-external-chain"
CALLER = make_test_caller(caller_id="m46-external-chain", roles=("demo_user",))


def _entry(key: str, content: str) -> CatalogEntry:
    """构造公开 active authority；title/key 只属于测试夹具，不进入 action 选择。"""

    return CatalogEntry(
        document_key=key,
        revision="r1",
        authority_ref=f"authority:{key}",
        source_kind="fixture",
        source_key=key,
        title=f"fixture-{key}",
        knowledge_type="policy",
        status="active",
        anchor="document",
        data_class="public_policy_text",
        purposes=("answer_evidence",),
        public=True,
        allowed_roles=frozenset(),
        content=content,
        content_identity=sha256(content.encode()).hexdigest(),
    )


def _evidence(entry: CatalogEntry, *, run_id: str = RUN_ID) -> Evidence:
    decision = authorize_document(
        caller=CALLER,
        entry=entry,
        purpose="answer_evidence",
        phase="pre_selection",
    )
    return make_document_evidence(
        run_id=run_id,
        release_identity=RELEASE,
        entry=entry,
        purpose="answer_evidence",
        authorization=decision,
        runtime_ref="m46-external-fixture",
    )


def _outcome(*evidence: Evidence, query: str, adapter_calls: int = 1) -> RetrievalOutcome:
    ledger = EvidenceLedger.from_candidates(run_id=evidence[0].ref.run_id, evidence=evidence)
    ledger = ledger.transition(
        evidence_ids=tuple(item.ref.evidence_id for item in evidence),
        to_stage="selected",
    )
    return RetrievalOutcome(
        execution_outcome="completed",
        reason_code="evidence_retrieved",
        selected_evidence=evidence,
        ledger=ledger,
        pre_generation_authorizations=(),
        diagnostics=RetrievalDiagnostics(
            run_ref=f"run:{query}",
            query_fingerprint=f"query:{query}",
            release_identity=RELEASE,
            corpus_identity="corpus-m46-external-fixture",
            adapter_identity="fixture-semantic",
            recipe_identity="fixture-recipe",
            adapter_calls=adapter_calls,
            authorized_entry_count=len(evidence),
            candidate_count=len(evidence),
            selected_count=len(evidence),
            elapsed_ms=1.0,
        ),
    )


@dataclass
class _InitialAcquirer:
    result: AcquisitionResult
    identity: str = "m46-fixture-initial"

    def acquire(self, *, request: RAGAnswerRequest, started_at: float) -> AcquisitionResult:
        del request, started_at
        return self.result


class _RewriteTool:
    """只响应两个 server-assembled focused query，证明没有 qst/static recipe 分支。"""

    def __init__(self, outcomes: dict[str, RetrievalOutcome]) -> None:
        self.outcomes = outcomes
        self.requests: list[str] = []

    def retrieve(self, request: KnowledgeRequest) -> RetrievalOutcome:
        self.requests.append(request.question)
        return self.outcomes[request.question]


@dataclass
class _SlotProvider:
    resolution: SlotResolution
    identity: str = "m46-fixture-external-formation"

    def resolve(self, *, request: RAGAnswerRequest, initial: RetrievalOutcome) -> SlotResolution:
        del request, initial
        return self.resolution


class _ExpansionAdapter:
    """initial 没有 sibling；只有 rewrite 新 fragment 才暴露相邻补全文档。"""

    identity = "m46-fixture-expansion"

    def __init__(self, expansion: Evidence, *, direct: bool = False) -> None:
        self.expansion = expansion
        self.direct = direct

    def preview(
        self,
        *,
        seeds: tuple[Evidence, ...],
        unsupported_slots: tuple[RequirementSlot, ...],
        caller: Any,
        purpose: str,
        max_seeds: int,
        max_sibling_units_scanned_per_seed: int,
        max_added: int,
    ) -> tuple[ExpansionPreview, ...]:
        del caller, purpose, max_seeds, max_sibling_units_scanned_per_seed, max_added
        if not unsupported_slots or not (
            self.direct or any(item.payload.document_key.startswith("rewrite-") for item in seeds)
        ):
            return ()
        return (ExpansionPreview(
            seed_evidence_id=seeds[0].ref.evidence_id,
            slot_identities=tuple(item.identity for item in unsupported_slots),
            opaque_candidates=(self.expansion,),
        ),)

    def materialize(
        self,
        *,
        previews: tuple[ExpansionPreview, ...],
        caller: Any,
        purpose: str,
        run_id: str,
        max_added: int,
    ) -> tuple[Evidence, ...]:
        del caller, purpose, run_id
        return tuple(
            item
            for preview in previews
            for item in preview.opaque_candidates[:max_added]
        )

    def preview_forward_continuation(
        self,
        *,
        seeds: tuple[Evidence, ...],
        procedure_slots: tuple[RequirementSlot, ...],
        caller: Any,
        purpose: str,
        max_seeds: int,
        max_added: int,
    ) -> tuple[ExpansionPreview, ...]:
        """procedure 已覆盖时，是否继续只由相邻 authority unit 的存在决定。"""

        del caller, purpose, max_seeds, max_added
        if not seeds or not procedure_slots:
            return ()
        return (ExpansionPreview(
            seed_evidence_id=seeds[0].ref.evidence_id,
            slot_identities=tuple(item.identity for item in procedure_slots),
            opaque_candidates=(self.expansion,),
        ),)


def test_external_chain_keeps_recovered_evidence_and_separates_child_budgets() -> None:
    """完整两步链必须留下 expansion/rewrite Evidence，而不是被3条 initial挤掉。"""

    entries = (
        _entry("initial-1", "alpha overview"),
        _entry("initial-2", "regional catalog"),
        _entry("initial-3", "general transfer policy"),
        _entry("rewrite-alpha", "alpha answer"),
        _entry("rewrite-beta", "beta overview fragment"),
        _entry("expansion-beta", "beta basis"),
    )
    evidence = {entry.document_key: _evidence(entry) for entry in entries}
    initial = _outcome(
        evidence["initial-1"], evidence["initial-2"], evidence["initial-3"], query="initial",
    )
    slot_alpha = RequirementSlot("alpha", "focused alpha", (("alpha",), ("answer",)))
    slot_beta = RequirementSlot("beta", "focused beta", (("beta",), ("basis",)))
    formed = tuple(FormedRequirement(
        slot=slot,
        supplier_identity="phase4b-b4-question-obligation-supplier-v1",
        formation_reason_category="requested_fact",
        allowed_recovery_actions=("query_rewrite_candidate", "context_expansion_candidate"),
    ) for slot in (slot_alpha, slot_beta))
    rewrite_tool = _RewriteTool({
        "focused alpha": _outcome(evidence["rewrite-alpha"], query="focused-alpha"),
        "focused beta": _outcome(evidence["rewrite-beta"], query="focused-beta"),
    })
    bundle = SimpleNamespace(
        release_identity=RELEASE,
        corpus_identity="corpus-m46-external-fixture",
        authorization_policy_identity="fixture-auth",
        outbound_policy_identity="fixture-outbound",
        entries=entries,
    )
    acquirer = BoundedRAGSubgraphAcquirer(
        initial_acquirer=_InitialAcquirer(AcquisitionResult(initial, {}, "fixture-initial")),
        knowledge_tool=rewrite_tool,  # type: ignore[arg-type] - 只消费公开 retrieve interface。
        active_loader=lambda: (object(), bundle),
        slot_provider=_SlotProvider(SlotResolution(
            slots=(slot_alpha, slot_beta),
            formed_requirements=formed,
            decision="structured_question_obligations",
            admission_reason_code="eligible",
        )),
        runtime_scope="external_profile",
        expansion_adapter=_ExpansionAdapter(evidence["expansion-beta"]),
    )

    result = acquirer.acquire(
        request=RAGAnswerRequest(question="alpha and beta", caller=CALLER, run_id=RUN_ID),
        started_at=0.0,
    )
    child = result.evidence_validity["subgraph"]
    final_keys = tuple(item.payload.document_key for item in result.outcome.selected_evidence)

    assert [item["action"] for item in child["attempts"]] == [
        "query_rewrite_candidate", "context_expansion_candidate",
    ]
    assert child["termination"] == "answer_ready"
    assert child["consumption"]["initial_retrieval_batches"] == 1
    assert child["consumption"]["rewrite_retrieval_batches"] == 2
    assert child["consumption"]["candidates_examined"] == 5
    assert child["consumption"]["expansion_candidates_scanned"] == 1
    assert final_keys == ("expansion-beta", "rewrite-alpha", "rewrite-beta")
    assert slot_alpha.supported_by(result.outcome.selected_evidence)
    assert slot_beta.supported_by(result.outcome.selected_evidence)
    assert rewrite_tool.requests == ["focused alpha", "focused beta"]


def test_external_procedure_uses_direct_forward_expansion_without_rewrite() -> None:
    """qst_0431 类 procedure：initial 已覆盖当前步骤时，直接取紧邻后续 unit。"""

    initial_entry = _entry("procedure-initial", "operational procedure rollback workflow steps")
    forward_entry = _entry("procedure-forward", "hosted and dedicated environment variants")
    initial_evidence = _evidence(initial_entry)
    forward_evidence = _evidence(forward_entry)
    initial = _outcome(initial_evidence, query="procedure-initial")
    slot = RequirementSlot(
        "procedure_core",
        "operational procedure rollback workflow steps",
        (("procedure", "steps", "workflow"),),
        marker_match_mode="token_overlap",
    )
    formed = FormedRequirement(
        slot=slot,
        supplier_identity="phase4b-b4-procedure-supplier-v1",
        formation_reason_category="requested_procedure",
        allowed_recovery_actions=("context_expansion_candidate",),
    )
    tool = _RewriteTool({})
    entries = (initial_entry, forward_entry)
    bundle = SimpleNamespace(
        release_identity=RELEASE,
        corpus_identity="corpus-m46-external-fixture",
        authorization_policy_identity="fixture-auth",
        outbound_policy_identity="fixture-outbound",
        entries=entries,
    )
    acquirer = BoundedRAGSubgraphAcquirer(
        initial_acquirer=_InitialAcquirer(AcquisitionResult(initial, {}, "fixture-initial")),
        knowledge_tool=tool,  # type: ignore[arg-type]
        active_loader=lambda: (object(), bundle),
        slot_provider=_SlotProvider(SlotResolution(
            slots=(slot,),
            formed_requirements=(formed,),
            continuation_policy="procedure_boundary_v1",
            decision="deterministic_procedure",
            admission_reason_code="eligible",
        )),
        runtime_scope="external_profile",
        expansion_adapter=_ExpansionAdapter(forward_evidence),
    )

    result = acquirer.acquire(
        request=RAGAnswerRequest(question="rollback procedure", caller=CALLER, run_id=RUN_ID),
        started_at=0.0,
    )
    child = result.evidence_validity["subgraph"]

    assert [item["action"] for item in child["attempts"]] == ["context_expansion_candidate"]
    assert child["attempts"][0]["eligible_actions"] == ["context_expansion_candidate", "stop"]
    assert child["consumption"]["rewrite_retrieval_batches"] == 0
    assert child["consumption"]["expansion_evidence_added"] == 1
    assert child["termination"] == "answer_ready"
    assert tool.requests == []


def test_external_noncanonical_gap_can_select_direct_expansion_from_observation() -> None:
    """qst_0461 类非 procedure 问题也能因真实 sibling preview 直扩，不靠 scenario 映射。"""

    initial_entry = _entry("incident-seed", "service incident overview")
    sibling_entry = _entry("incident-detail", "regional impact basis")
    initial_evidence = _evidence(initial_entry)
    sibling_evidence = _evidence(sibling_entry)
    initial = _outcome(initial_evidence, query="incident")
    slot = RequirementSlot("impact", "regional impact basis", (("regional",), ("basis",)))
    formed = FormedRequirement(
        slot=slot,
        supplier_identity="phase4b-b4-question-obligation-supplier-v1",
        formation_reason_category="requested_fact",
        allowed_recovery_actions=("query_rewrite_candidate", "context_expansion_candidate"),
    )
    bundle = SimpleNamespace(
        release_identity=RELEASE,
        corpus_identity="corpus-m46-external-fixture",
        authorization_policy_identity="fixture-auth",
        outbound_policy_identity="fixture-outbound",
        entries=(initial_entry, sibling_entry),
    )
    tool = _RewriteTool({})
    acquirer = BoundedRAGSubgraphAcquirer(
        initial_acquirer=_InitialAcquirer(AcquisitionResult(initial, {}, "fixture-initial")),
        knowledge_tool=tool,  # type: ignore[arg-type]
        active_loader=lambda: (object(), bundle),
        slot_provider=_SlotProvider(SlotResolution(
            slots=(slot,), formed_requirements=(formed,),
            decision="structured_question_obligations", admission_reason_code="eligible",
        )),
        runtime_scope="external_profile",
        expansion_adapter=_ExpansionAdapter(sibling_evidence, direct=True),
    )

    result = acquirer.acquire(
        request=RAGAnswerRequest(question="regional incident impact", caller=CALLER, run_id=RUN_ID),
        started_at=0.0,
    )
    child = result.evidence_validity["subgraph"]

    assert [item["action"] for item in child["attempts"]] == ["context_expansion_candidate"]
    assert child["termination"] == "answer_ready"
    assert tool.requests == []


def test_subgraph_contract_failure_clears_partial_initial_before_answer_gate() -> None:
    """formation/graph失败时initial只是诊断素材，不能继续生成看似complete的旧答案。"""

    entry = _entry("initial-only", "outdated alpha answer")
    initial = _outcome(_evidence(entry), query="initial")
    bundle = SimpleNamespace(
        release_identity=RELEASE,
        corpus_identity="corpus-m46-external-fixture",
        authorization_policy_identity="fixture-auth",
        outbound_policy_identity="fixture-outbound",
        entries=(entry,),
    )
    acquirer = BoundedRAGSubgraphAcquirer(
        initial_acquirer=_InitialAcquirer(AcquisitionResult(initial, {}, "fixture-initial")),
        knowledge_tool=_RewriteTool({}),  # type: ignore[arg-type]
        active_loader=lambda: (object(), bundle),
        slot_provider=_SlotProvider(SlotResolution(
            slots=(),
            decision="structured_supplier_failed",
            admission_reason_code="fixture_failure",
            failure_reason="fixture_failure",
        )),
        runtime_scope="external_profile",
    )

    result = acquirer.acquire(
        request=RAGAnswerRequest(question="alpha", caller=CALLER, run_id=RUN_ID),
        started_at=0.0,
    )

    assert result.evidence_validity["subgraph"]["termination"] == "contract_failure"
    assert result.outcome.execution_outcome == "external_unavailable"
    assert result.outcome.reason_code == "retrieval_unavailable"
    assert result.outcome.selected_evidence == ()
    assert result.outcome.pre_generation_authorizations == ()


def test_execute_exception_projects_safe_stage_and_marks_attempts_unobserved() -> None:
    """异常正文保持私有，但下一次Probe能区分execute/tool合同失败和真正零调用。"""

    class _FailingTool:
        def retrieve(self, request: KnowledgeRequest) -> RetrievalOutcome:
            del request
            raise KnowledgeToolContractError("fixture_private_reason", "must-not-leak")

    entry = _entry("initial-only", "alpha overview")
    initial = _outcome(_evidence(entry), query="initial")
    slot = RequirementSlot("alpha", "focused alpha", (("alpha",), ("answer",)))
    formed = FormedRequirement(
        slot=slot,
        supplier_identity="phase4b-b4-question-obligation-supplier-v1",
        formation_reason_category="requested_fact",
        allowed_recovery_actions=("query_rewrite_candidate",),
    )
    acquirer = BoundedRAGSubgraphAcquirer(
        initial_acquirer=_InitialAcquirer(AcquisitionResult(initial, {}, "fixture-initial")),
        knowledge_tool=_FailingTool(),  # type: ignore[arg-type]
        active_loader=lambda: (object(), SimpleNamespace(entries=(entry,))),
        slot_provider=_SlotProvider(SlotResolution(
            slots=(slot,),
            formed_requirements=(formed,),
            decision="structured_question_obligations",
            admission_reason_code="eligible",
        )),
        runtime_scope="external_profile",
    )

    result = acquirer.acquire(
        request=RAGAnswerRequest(question="alpha", caller=CALLER, run_id=RUN_ID),
        started_at=0.0,
    )
    child = result.evidence_validity["subgraph"]

    assert child["detail_code"] == "subgraph_execute_knowledge_tool_contract_failure"
    assert child["consumption"]["retrieval_attempts_observed"] is False
    assert "must-not-leak" not in str(child)
    assert "fixture_private_reason" not in str(child)
    assert result.outcome.selected_evidence == ()
