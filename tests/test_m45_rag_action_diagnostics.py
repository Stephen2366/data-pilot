"""M45-A/B：failure funnel、campaign/artifact 与 deterministic rewrite 合同。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest

from engine.governance import (
    OutboundRequest,
    authorize_document,
    decide_outbound,
    test_caller as make_test_caller,
)
from engine.phase4b.identity import canonical_hash
from engine.phase4b.rag_diagnostics import (
    RAGRecoveryDiagnostic,
    RecoveryExecution,
    RecoveryObservation,
    RequirementSlot,
    project_failure_funnel,
)
from engine.phase4b.rag_enterprise_diagnostics import EnterpriseSiblingExpansionAdapter
from engine.phase4b.rag_requirement_proposal import (
    EvidenceAwareRequirementProposer,
    PROPOSAL_DATA_CLASS,
    PROPOSAL_OUTBOUND_POLICY,
    PROPOSAL_PURPOSE,
    RequirementProposalError,
)
from engine.phase4b.loop_contracts import EvidenceDelta, ProgressDecision, ResourceConsumption
from engine.rag.catalog import CatalogEntry
from engine.rag.evidence import (
    DocumentContextCoordinates,
    DocumentEvidencePayload,
    EvidenceLedger,
    make_document_evidence,
)
from engine.rag.enterprise_runtime import EnterpriseContextLoader
from engine.rag.knowledge_tool import (
    KnowledgeRequest,
    RetrievalDiagnostics,
    RetrievalOutcome,
)
from eval.rag_action_diagnostics import (
    RAGActionDiagnosticError,
    build_completed_artifact,
    build_continuation_review_artifact,
    build_repair_review_artifact,
    build_reopened_review_artifact,
    build_review_artifact,
    load_continuation_diagnostic_campaign,
    load_diagnostic_campaign,
    load_reopened_diagnostic_campaign,
    load_repair_diagnostic_campaign,
    validate_completed_artifact,
    validate_continuation_review_artifact,
    validate_repair_review_artifact,
    validate_review_artifact,
    validate_reopened_review_artifact,
)
from scripts.probe_m45_b3 import _external_slots


def _entry(key: str, content: str) -> CatalogEntry:
    """构造公开测试文档；key 只用于测试，不参与 slot 支持判断。"""

    import hashlib

    return CatalogEntry(
        document_key=key,
        revision="r1",
        authority_ref=f"authority:{key}",
        source_kind="policy_markdown",
        source_key=key,
        title=f"title-{key}",
        knowledge_type="policy",
        status="active",
        anchor="document",
        data_class="role_restricted_policy_text",
        purposes=("answer_evidence",),
        public=True,
        allowed_roles=frozenset(),
        content=content,
        content_identity=hashlib.sha256(content.encode()).hexdigest(),
    )


def _evidence(
    key: str,
    content: str,
    *,
    run_id: str,
    coordinates: DocumentContextCoordinates | None = None,
) -> Any:
    caller = make_test_caller(caller_id="m45-test", roles=("ops", "customer_service"))
    entry = _entry(key, content)
    decision = authorize_document(
        caller=caller, entry=entry, purpose="answer_evidence", phase="pre_selection"
    )
    return make_document_evidence(
        run_id=run_id,
        release_identity="release-m45",
        entry=entry,
        purpose="answer_evidence",
        authorization=decision,
        runtime_ref="fake-retrieval-v1",
        context_coordinates=coordinates,
    )


def _outcome(*evidence: Any, query: str = "initial") -> RetrievalOutcome:
    ledger = EvidenceLedger.from_candidates(run_id=evidence[0].ref.run_id if evidence else "empty", evidence=evidence)
    if evidence:
        ledger = ledger.transition(
            evidence_ids=tuple(item.ref.evidence_id for item in evidence), to_stage="selected"
        )
    return RetrievalOutcome(
        execution_outcome="completed",
        reason_code="evidence_retrieved" if evidence else "no_candidate",
        selected_evidence=tuple(evidence),
        ledger=ledger,
        pre_generation_authorizations=(),
        diagnostics=RetrievalDiagnostics(
            run_ref="run:fake",
            query_fingerprint=f"fp:{query}",
            release_identity="release-m45",
            corpus_identity="corpus-m45",
            adapter_identity="fake-adapter-v1",
            recipe_identity="fake-recipe-v1",
            adapter_calls=1,
            authorized_entry_count=2,
            candidate_count=len(evidence),
            selected_count=len(evidence),
            elapsed_ms=1.0,
        ),
    )


class _FakeTool:
    """通过 Knowledge Tool interface 测试深模块，不让测试进入内部选择实现。"""

    def __init__(self, outcomes: dict[str, RetrievalOutcome]) -> None:
        self.outcomes = outcomes
        self.requests: list[KnowledgeRequest] = []

    def retrieve(self, request: KnowledgeRequest) -> RetrievalOutcome:
        self.requests.append(request)
        return self.outcomes[request.question]


def _request(question: str = "initial") -> KnowledgeRequest:
    return KnowledgeRequest(
        question=question,
        caller=make_test_caller(caller_id="m45-test", roles=("ops", "customer_service")),
        purpose="answer_evidence",
        run_id="m45-run",
    )


def _slot(identity: str, query: str, *markers: str) -> RequirementSlot:
    return RequirementSlot(identity, query, tuple((marker,) for marker in markers))


def test_failure_funnel_propagates_not_observed_after_first_failure() -> None:
    funnel = project_failure_funnel({
        "retrieved": True,
        "selected": False,
        "generation_visible": True,  # 下游值即使存在也不能越过失败层。
        "support": True,
        "cited": True,
        "answer": True,
    })
    assert funnel.first_failure_layer == "selected"
    assert dict(funnel.stages) == {
        "retrieved": "passed",
        "selected": "failed",
        "generation_visible": "not_observed",
        "support": "not_observed",
        "cited": "not_observed",
        "answer": "not_observed",
    }


def test_campaign_manifest_is_closed_world_and_reserve_remains_sealed() -> None:
    campaign = load_diagnostic_campaign()
    assert campaign.identity == "469b5ec01eb78d839e2c621378f53bab0cd29cebc3488f78c9475b13bd2312fe"
    assert tuple(campaign.by_id()) == ("T4", "qst_0420", "qst_0431", "qst_0461")
    assert campaign.reserve["required_access_state"] == "sealed"


def test_reopened_campaign_is_additive_and_freezes_proposal_budget() -> None:
    original = load_diagnostic_campaign()
    reopened = load_reopened_diagnostic_campaign()
    assert reopened.identity == "c86e38705382b03d9a99d4349a319be9561d6731b887f01307ad3ddda3f7eaea"
    assert reopened.predecessor_campaign_identity == original.identity
    assert reopened.budget["max_embedding_provider_attempts"] == 8
    assert reopened.budget["max_chat_model_calls"] == 2
    assert reopened.budget["max_chat_tokens"] == 8000
    assert reopened.budget["max_total_provider_attempts"] == 10
    assert reopened.proposal == {
        "prompt_identity": "m45-e-evidence-aware-requirement-proposal-v1",
        "outbound_policy_identity": "phase4b-m45-rag-requirement-proposal-outbound-v1",
        "receiver": "qwen_chat",
        "purpose": "rag_requirement_proposal",
        "data_class": "public_benchmark_question_with_authorized_evidence",
        "model": "qwen3.7-plus",
        "max_evidence": 3,
        "max_evidence_chars_each": 4000,
        "max_completion_tokens_each": 1600,
    }


def test_repair_campaign_allows_only_offline_461_and_one_431_call() -> None:
    reopened = load_reopened_diagnostic_campaign()
    repair = load_repair_diagnostic_campaign()
    assert repair.identity == "b41c0d98d330bbf68b6b17d95441e044b9a27c0f66b8ca6594571f5dddcf37a5"
    assert repair.predecessor_campaign_identity == reopened.identity
    assert tuple(repair.by_id()) == ("qst_0461", "qst_0431")
    assert repair.budget["max_chat_model_calls"] == 1
    assert repair.budget["max_chat_tokens"] == 4123
    assert repair.budget["max_total_provider_attempts"] == 11
    assert repair.repair == {
        "offline_replay_scenario": "qst_0461",
        "provider_revalidation_scenario": "qst_0431",
        "marker_match_mode": "token_overlap",
        "legacy_marker_match_mode": "exact",
        "provider_retry_limit": 0,
    }


def test_continuation_campaign_is_single_scenario_and_zero_provider() -> None:
    campaign = load_continuation_diagnostic_campaign()
    assert campaign.identity == "15cda06ec378b8a200e5aa6edd1b38e3af23cc256269fc07629873def36be708"
    assert tuple(campaign.by_id()) == ("qst_0431",)
    assert campaign.predecessor_campaign_identity == load_repair_diagnostic_campaign().identity
    assert campaign.budget["max_chat_model_calls"] == 0
    assert campaign.budget["max_embedding_provider_attempts"] == 0
    assert campaign.budget["max_total_provider_attempts"] == 11
    assert campaign.continuation == {
        "policy": "procedure_boundary_v1",
        "intent_tokens": ["procedure", "workflow", "steps", "checklist"],
        "direction": "forward_only",
        "max_forward_units_per_seed": 1,
        "requires_authority_coordinates": True,
    }


def test_external_requirement_slots_do_not_embed_gold_answer_or_document_hints() -> None:
    """typed requirement 可保留问题实体，但不得把答案值或 gold 身份伪装成 rewrite。"""

    forbidden = {
        "0.085", "sampled bytes", "provider-billed", "30 minutes", "60 minutes",
        "14 days", "friday", "4pm", "4 pm",
        "dsid_4e65166659394a90922be6a5c7b110a8",
        "dsid_7b2f4b37dfb642e19d78c5f9d2c43f16",
        "operator fallback experiment matrix",
    }
    serialized = "\n".join(
        (slot.focused_query + "\n" + "\n".join(marker for group in slot.support_marker_groups for marker in group)).casefold()
        for scenario_id in ("qst_0420", "qst_0431", "qst_0461")
        for slot in _external_slots(scenario_id)
    )
    assert not {item for item in forbidden if item in serialized}


def test_rewrite_uses_only_unsupported_presigned_slot_and_adds_new_evidence() -> None:
    initial = _evidence("quality", "质量问题需要检测报告和商品照片", run_id="initial")
    duplicate = _evidence("quality", "质量问题需要检测报告和商品照片", run_id="child-1")
    added = _evidence("basic", "全额退款需要订单号、付款凭证并满足基础退款范围", run_id="child-1")
    tool = _FakeTool({
        "initial": _outcome(initial, query="initial"),
        "基础退款适用范围和受理材料": _outcome(duplicate, added, query="focused"),
    })
    slots = (
        _slot("quality_conditions", "质量问题处理前提", "检测报告", "商品照片"),
        _slot("policy_scope_materials", "基础退款适用范围和受理材料", "全额退款", "订单号"),
    )
    diagnostic = RAGRecoveryDiagnostic()
    observation = diagnostic.observe(
        scenario_id="T4",
        runtime_scope="business_release",
        slots=slots,
        tool=tool,  # type: ignore[arg-type]
        request=_request(),
    )
    assert observation.unsupported_slot_identities == ("policy_scope_materials",)
    assert observation.eligible_actions == ("query_rewrite_candidate", "stop")
    assert observation.rejected_actions == ("context_expansion_candidate",)

    result = diagnostic.execute(
        observation=observation,
        slots=slots,
        tool=tool,  # type: ignore[arg-type]
        request=_request(),
    )
    assert result.chosen_action == "query_rewrite_candidate"
    assert result.evidence_delta.gained
    assert len(result.evidence_delta.added) == 1
    assert len(result.evidence_delta.duplicate) == 1
    assert result.consumed.retrieval_batches == 1
    assert result.consumed.model_calls == result.consumed.total_tokens == 0
    assert [item.question for item in tool.requests] == ["initial", "基础退款适用范围和受理材料"]


def test_all_slots_supported_stops_without_second_retrieval() -> None:
    initial = _evidence("complete", "全额退款需要订单号和检测报告", run_id="initial")
    tool = _FakeTool({"initial": _outcome(initial)})
    slots = (_slot("complete", "不应执行", "全额退款", "订单号", "检测报告"),)
    diagnostic = RAGRecoveryDiagnostic()
    observation = diagnostic.observe(
        scenario_id="T4", runtime_scope="business_release", slots=slots,
        tool=tool, request=_request(),  # type: ignore[arg-type]
    )
    result = diagnostic.execute(
        observation=observation, slots=slots, tool=tool, request=_request(),  # type: ignore[arg-type]
    )
    assert observation.eligible_actions == ("stop",)
    assert result.chosen_action == "stop"
    assert not result.evidence_delta.gained
    assert len(tool.requests) == 1


def test_sqlite_sibling_loader_is_bounded_and_never_crosses_physical_document() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE units (unit_identity TEXT, physical_source_identity TEXT, normalized_start INTEGER, normalized_end INTEGER)"
    )
    connection.executemany(
        "INSERT INTO units VALUES (?, ?, ?, ?)",
        (
            ("u1", "physical-a", 0, 10),
            ("u2", "physical-a", 10, 20),
            ("u3", "physical-a", 20, 30),
            ("other", "physical-b", 0, 10),
        ),
    )
    loader = EnterpriseContextLoader(connection)
    coordinates = DocumentContextCoordinates("confluence", "doc-a", "physical-a", "u2", 10, 20)
    assert loader.sibling_unit_identities(coordinates, max_units=8) == ("u1", "u3")
    assert loader.following_sibling_unit_identity(coordinates) == "u3"
    assert loader.following_sibling_unit_identity(
        DocumentContextCoordinates("confluence", "doc-a", "physical-a", "u3", 20, 30)
    ) is None


class _FakeContextLoader:
    """组合测试 adapter 逻辑；SQLite 顺序已由独立测试覆盖。"""

    def __init__(
        self,
        contexts: dict[str, tuple[CatalogEntry, DocumentContextCoordinates]],
        *,
        siblings: tuple[str, ...] = ("neighbor",),
    ) -> None:
        self.contexts = contexts
        self.siblings = siblings

    def sibling_unit_identities(
        self, coordinates: DocumentContextCoordinates, *, max_units: int,
    ) -> tuple[str, ...]:
        assert coordinates.physical_source_identity == "physical-a"
        assert max_units == 8
        return self.siblings[:max_units]

    def following_sibling_unit_identity(
        self, coordinates: DocumentContextCoordinates,
    ) -> str | None:
        assert coordinates.physical_source_identity == "physical-a"
        return self.siblings[0] if self.siblings else None

    def __call__(self, entry: CatalogEntry) -> Any:
        materialized, coordinates = self.contexts[entry.document_key.removeprefix("enterprise-unit:")]
        return SimpleNamespace(entry=materialized, coordinates=coordinates)


def test_external_fragment_observation_selects_expansion_and_reauthorizes_neighbor() -> None:
    seed_coordinates = DocumentContextCoordinates("confluence", "doc-a", "physical-a", "seed", 0, 20)
    neighbor_coordinates = DocumentContextCoordinates("confluence", "doc-a", "physical-a", "neighbor", 20, 40)
    seed = _evidence("enterprise-unit:seed", "Hosted rollback starts by freezing rollout", run_id="initial", coordinates=seed_coordinates)
    neighbor_metadata = replace(
        _entry("enterprise-unit:neighbor", ""),
        source_kind="confluence",
        source_key="physical-a",
        data_class="public_benchmark_document",
        purposes=("answer_evidence", "generation_context"),
        content_identity=_entry("x", "Dedicated clusters redeploy and customer communication").content_identity,
    )
    neighbor_content = replace(
        neighbor_metadata,
        content="Dedicated clusters redeploy and customer communication",
        content_identity=_entry("x", "Dedicated clusters redeploy and customer communication").content_identity,
    )
    runtime = SimpleNamespace(
        bundle=SimpleNamespace(
            release_identity="profile-m45",
            entries=(neighbor_metadata,),
        ),
        context_loader=_FakeContextLoader({"neighbor": (neighbor_content, neighbor_coordinates)}),
        manifest=SimpleNamespace(profile_identity="profile-m45", unit_recipe_identity="unit-recipe-m45"),
    )
    adapter = EnterpriseSiblingExpansionAdapter(runtime)  # type: ignore[arg-type]
    tool = _FakeTool({"initial": _outcome(seed)})
    slots = (
        _slot("hosted", "Hosted rollback", "Hosted", "freezing rollout"),
        _slot("dedicated", "Dedicated rollback", "Dedicated clusters", "customer communication"),
    )
    diagnostic = RAGRecoveryDiagnostic()
    observation = diagnostic.observe(
        scenario_id="qst_0431", runtime_scope="external_profile", slots=slots,
        tool=tool, request=_request(), expansion_adapter=adapter,  # type: ignore[arg-type]
    )
    assert observation.eligible_actions == ("context_expansion_candidate", "stop")
    assert observation.rejected_actions == ("query_rewrite_candidate",)
    result = diagnostic.execute(
        observation=observation, slots=slots, tool=tool, request=_request(),
        expansion_adapter=adapter,  # type: ignore[arg-type]
    )
    assert result.chosen_action == "context_expansion_candidate"
    assert len(result.added_evidence) == 1
    assert result.consumed.retrieval_batches == result.consumed.model_calls == 0
    assert result.added_evidence[0].payload.context_coordinates == neighbor_coordinates


def test_procedure_boundary_expands_forward_when_coverage_looks_complete() -> None:
    """M45-H：答案词都出现也不等于 procedure fragment 已到物理文档末尾。"""

    seed_coordinates = DocumentContextCoordinates(
        "confluence", "doc-a", "physical-a", "seed", 0, 20,
    )
    next_coordinates = DocumentContextCoordinates(
        "confluence", "doc-a", "physical-a", "next", 20, 40,
    )
    seed = _evidence(
        "enterprise-unit:seed",
        "Serving Runtime emergency rollback procedure for Hosted and Dedicated. Step 1: freeze.",
        run_id="structural",
        coordinates=seed_coordinates,
    )
    next_text = "Step 2: pin the tag. Step 3: redeploy and verify health."
    next_metadata = replace(
        _entry("enterprise-unit:next", ""),
        source_kind="confluence",
        source_key="physical-a",
        data_class="public_benchmark_document",
        purposes=("answer_evidence", "generation_context"),
        content_identity=_entry("x", next_text).content_identity,
    )
    runtime = SimpleNamespace(
        bundle=SimpleNamespace(release_identity="profile-m45", entries=(next_metadata,)),
        context_loader=_FakeContextLoader({
            "next": (replace(next_metadata, content=next_text), next_coordinates),
        }, siblings=("next",)),
        manifest=SimpleNamespace(profile_identity="profile-m45", unit_recipe_identity="unit-recipe"),
    )
    slots = (_slot(
        "rollback", "Serving Runtime emergency rollback procedure",
        "Serving Runtime", "emergency", "rollback",
    ),)
    diagnostic = RAGRecoveryDiagnostic()
    adapter = EnterpriseSiblingExpansionAdapter(runtime)  # type: ignore[arg-type]
    initial = _outcome(seed)

    # 默认合同保持旧行为；只有显式 v1 policy 才改变 action admission。
    old = diagnostic.observe_existing(
        scenario_id="qst_0431", runtime_scope="external_profile", slots=slots,
        initial=initial, request=_request(), expansion_adapter=adapter,
    )
    assert old.eligible_actions == ("stop",)

    observation = diagnostic.observe_existing(
        scenario_id="qst_0431", runtime_scope="external_profile", slots=slots,
        initial=initial, request=_request(), expansion_adapter=adapter,
        continuation_policy="procedure_boundary_v1",
    )
    assert observation.unsupported_slot_identities == ()
    assert observation.eligible_actions == ("context_expansion_candidate", "stop")
    assert observation.trigger_reason_codes == ("procedure_forward_unit_available",)
    result = diagnostic.execute(
        observation=observation, slots=slots, tool=_FakeTool({}), request=_request(),
        expansion_adapter=adapter,  # type: ignore[arg-type]
    )
    assert result.evidence_delta.gained
    assert result.added_evidence[0].payload.context_coordinates == next_coordinates
    assert result.consumed.retrieval_batches == result.consumed.model_calls == 0


def test_procedure_boundary_rejects_non_procedure_and_last_unit() -> None:
    coordinates = DocumentContextCoordinates(
        "confluence", "doc-a", "physical-a", "seed", 0, 20,
    )
    seed = _evidence(
        "enterprise-unit:seed", "Hosted rollback status is complete.",
        run_id="structural-negative", coordinates=coordinates,
    )
    runtime = SimpleNamespace(
        bundle=SimpleNamespace(release_identity="profile-m45", entries=()),
        context_loader=_FakeContextLoader({}, siblings=()),
        manifest=SimpleNamespace(profile_identity="profile-m45", unit_recipe_identity="unit-recipe"),
    )
    adapter = EnterpriseSiblingExpansionAdapter(runtime)  # type: ignore[arg-type]
    diagnostic = RAGRecoveryDiagnostic()
    for focused_query in ("Hosted rollback status", "Hosted rollback procedure"):
        observation = diagnostic.observe_existing(
            scenario_id="negative", runtime_scope="external_profile",
            slots=(_slot("rollback", focused_query, "Hosted", "rollback"),),
            initial=_outcome(seed), request=_request(), expansion_adapter=adapter,
            continuation_policy="procedure_boundary_v1",
        )
        assert observation.eligible_actions == ("stop",)
        assert observation.trigger_reason_codes == ()


def test_sibling_expansion_selects_minimum_joint_support_subset() -> None:
    """seed+多个 sibling 可联合闭合 slot；不加入夹在中间但不贡献 coverage 的 unit。"""

    seed_coordinates = DocumentContextCoordinates("google_drive", "doc-a", "physical-a", "seed", 0, 20)
    seed = _evidence(
        "enterprise-unit:seed",
        "updated egress measurement basis from billing records",
        run_id="m45-run",
        coordinates=seed_coordinates,
    )

    def sibling(unit: str, start: int, content: str) -> tuple[CatalogEntry, DocumentContextCoordinates]:
        metadata = replace(
            _entry(f"enterprise-unit:{unit}", ""),
            source_kind="google_drive",
            source_key="physical-a",
            data_class="public_benchmark_document",
            purposes=("answer_evidence", "generation_context"),
            content_identity=_entry("x", content).content_identity,
        )
        return (
            replace(metadata, content=content),
            DocumentContextCoordinates("google_drive", "doc-a", "physical-a", unit, start, start + 20),
        )

    contexts = {
        "overview": sibling("overview", 20, "EXP-002 regional egress experiment overview"),
        "irrelevant": sibling("irrelevant", 40, "operator ownership and contact list"),
        "rate": sibling("rate", 60, "current cost rate is $0.10 USD per GiB"),
    }
    runtime = SimpleNamespace(
        bundle=SimpleNamespace(
            release_identity="profile-m45",
            entries=tuple(item[0] for item in contexts.values()),
        ),
        context_loader=_FakeContextLoader(
            contexts, siblings=("overview", "irrelevant", "rate"),
        ),
        manifest=SimpleNamespace(profile_identity="profile-m45", unit_recipe_identity="unit-recipe-m45"),
    )
    slots = (
        RequirementSlot(
            "current_egress_rate",
            "EXP-002 current authoritative egress cost rate catalog",
            (("exp-002",), ("egress",), ("rate", "cost"), ("current", "updated")),
        ),
        RequirementSlot(
            "measurement_basis",
            "EXP-002 current egress measurement basis",
            (("exp-002",), ("egress",), ("measurement", "billing"), ("current", "updated")),
        ),
    )
    tool = _FakeTool({"initial": _outcome(seed)})
    diagnostic = RAGRecoveryDiagnostic()
    adapter = EnterpriseSiblingExpansionAdapter(runtime)  # type: ignore[arg-type]
    observation = diagnostic.observe(
        scenario_id="qst_0420", runtime_scope="external_profile", slots=slots,
        tool=tool, request=_request(), expansion_adapter=adapter,  # type: ignore[arg-type]
    )
    result = diagnostic.execute(
        observation=observation, slots=slots, tool=tool, request=_request(),
        expansion_adapter=adapter,  # type: ignore[arg-type]
    )
    added_units = {
        item.payload.context_coordinates.unit_identity
        for item in result.added_evidence
        if isinstance(item.payload, DocumentEvidencePayload)
        and item.payload.context_coordinates is not None
    }
    assert observation.eligible_actions == ("context_expansion_candidate", "stop")
    assert added_units == {"overview", "rate"}


def test_continuation_ranks_rewrite_fragment_then_expands_without_retrieval() -> None:
    """第二步只消费 prior EvidenceDelta；相关 seed 即使原顺序第三也能进入 2-seed 上限。"""

    coordinates = DocumentContextCoordinates("confluence", "doc-a", "physical-a", "seed", 0, 20)
    irrelevant_1 = _evidence("irrelevant-1", "kitchen cleanup", run_id="m45-run")
    irrelevant_2 = _evidence("irrelevant-2", "runtime rollback", run_id="m45-run")
    relevant = _evidence(
        "enterprise-unit:seed",
        "EXP-002 egress cost penalty catalog update overview",
        run_id="m45-run",
        coordinates=coordinates,
    )
    ranked = EnterpriseSiblingExpansionAdapter._rank_seeds(
        (irrelevant_1, irrelevant_2, relevant),
        (RequirementSlot(
            "current_egress_rate",
            "EXP-002 current egress cost rate catalog",
            (("exp-002",), ("egress",), ("rate", "cost"), ("current", "update")),
        ),),
    )
    assert ranked[0] is relevant

    neighbor_coordinates = DocumentContextCoordinates(
        "confluence", "doc-a", "physical-a", "neighbor", 20, 40
    )
    neighbor_metadata = replace(
        _entry("enterprise-unit:neighbor", ""),
        source_kind="confluence",
        source_key="physical-a",
        data_class="public_benchmark_document",
        purposes=("answer_evidence", "generation_context"),
        content_identity=_entry("x", "$0.10 USD current rate").content_identity,
    )
    neighbor_content = replace(
        neighbor_metadata,
        content="$0.10 USD current rate",
        content_identity=_entry("x", "$0.10 USD current rate").content_identity,
    )
    runtime = SimpleNamespace(
        bundle=SimpleNamespace(release_identity="profile-m45", entries=(neighbor_metadata,)),
        context_loader=_FakeContextLoader({"neighbor": (neighbor_content, neighbor_coordinates)}),
        manifest=SimpleNamespace(profile_identity="profile-m45", unit_recipe_identity="unit-recipe-m45"),
    )
    adapter = EnterpriseSiblingExpansionAdapter(runtime)  # type: ignore[arg-type]
    slots = (RequirementSlot(
        "current_egress_rate",
        "EXP-002 current egress cost rate catalog",
        (("exp-002",), ("egress",), ("rate", "cost"), ("current", "update")),
    ),)
    initial = _outcome(_evidence("old", "old catalog", run_id="m45-run"))
    prior_observation = RecoveryObservation(
        scenario_id="qst_0420",
        runtime_scope="external_profile",
        requirement_signature=canonical_hash([item.signature for item in slots]),
        initial_outcome=initial,
        unsupported_slot_identities=("current_egress_rate",),
        eligible_actions=("query_rewrite_candidate", "stop"),
        rejected_actions=("context_expansion_candidate",),
    )
    prior = RecoveryExecution(
        observation=prior_observation,
        chosen_action="query_rewrite_candidate",
        status="completed",
        evidence_delta=EvidenceDelta(added=(relevant.ref.audit_projection(),)),
        consumed=ResourceConsumption(actions=1, retrieval_batches=1, token_usage_observed=True),
        progress=ProgressDecision(True, True, "evidence_gain"),
        duplicate_key="rewrite-once",
        termination_reason="action_completed",
        elapsed_ms=1.0,
        added_evidence=(irrelevant_1, irrelevant_2, relevant),
    )
    diagnostic = RAGRecoveryDiagnostic()
    observation = diagnostic.observe_after_rewrite(
        prior=prior, slots=slots, expansion_adapter=adapter, request=_request(),
    )
    assert observation.eligible_actions == ("context_expansion_candidate", "stop")
    assert observation.rejected_actions == ("query_rewrite_candidate",)
    result = diagnostic.execute(
        observation=observation, slots=slots, tool=_FakeTool({}), request=_request(),
        expansion_adapter=adapter,  # type: ignore[arg-type]
    )
    assert result.chosen_action == "context_expansion_candidate"
    assert result.consumed.retrieval_batches == 0
    assert len(result.added_evidence) == 1


def _completed_execution(scenario_id: str, action: str, outcome: RetrievalOutcome) -> RecoveryExecution:
    wrong = "context_expansion_candidate" if action == "query_rewrite_candidate" else "query_rewrite_candidate"
    observation = RecoveryObservation(
        scenario_id=scenario_id,
        runtime_scope="business_release" if scenario_id == "T4" else "external_profile",
        requirement_signature=f"req-{scenario_id}",
        initial_outcome=outcome,
        unsupported_slot_identities=("slot",),
        eligible_actions=(action, "stop"),  # type: ignore[arg-type]
        rejected_actions=(wrong,),  # type: ignore[arg-type]
    )
    return RecoveryExecution(
        observation=observation,
        chosen_action=action,  # type: ignore[arg-type]
        status="completed",
        evidence_delta=EvidenceDelta(added=({"evidence_id": f"added-{scenario_id}"},)),
        consumed=ResourceConsumption(actions=1, model_calls=0, total_tokens=0, token_usage_observed=True),
        progress=ProgressDecision(True, False, "evidence_gain"),
        duplicate_key=f"dup-{scenario_id}",
        termination_reason="action_completed",
        elapsed_ms=1.0,
    )


def test_completed_artifact_requires_both_cards_same_runtime_and_all_probes() -> None:
    campaign = load_diagnostic_campaign()
    outcome = _outcome(_evidence("seed", "seed", run_id="seed"))
    executions = tuple(
        _completed_execution(spec.scenario_id, spec.expected_action, outcome)
        for spec in campaign.scenarios
    )
    runtime = {"identity": "same-semantic", "profile": "same-profile"}
    artifact = build_completed_artifact(
        campaign=campaign,
        executions=executions,
        runtime_identities={
            "T4": {"identity": "business"},
            "qst_0420": runtime,
            "qst_0431": runtime,
            "qst_0461": runtime,
        },
        probe_evidence={
            "M45-P1": {"status": "passed"},
            "M45-P2": {"status": "passed"},
            "M45-P3": {"status": "passed"},
        },
        external_artifact_manifest={"sha256": "a" * 64},
    )
    assert artifact["qualification"]["decision"] == "go_for_M46"
    validate_completed_artifact(artifact, campaign=campaign)

    tampered = dict(artifact)
    tampered["reserve_access_state"] = "opened"
    with pytest.raises(RAGActionDiagnosticError):
        validate_completed_artifact(tampered, campaign=campaign)


def test_review_artifact_derives_no_go_from_direct_expansion_trigger_failure() -> None:
    campaign = load_diagnostic_campaign()

    def signed(payload: dict[str, Any]) -> dict[str, Any]:
        payload["artifact_identity"] = canonical_hash(payload)
        return payload

    common = {
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "decision": "continue",
        "reserve_access_state": "sealed",
    }
    probes = {
        "M45-P1": signed({**common, "probe_id": "M45-P1", "gate": "passed", "usage": {"embedding_provider_attempts": 0}}),
        "M45-P2-R1": signed({**common, "probe_id": "M45-P2", "gate": "failed", "usage": {"embedding_provider_attempts": 3}}),
        "M45-P2-R2": signed({
            **common,
            "probe_id": "M45-P2",
            "gate": "failed",
            "usage": {"embedding_provider_attempts": 3},
            "scenarios": [{
                "execution": {"chosen_action": "query_rewrite_candidate"},
                "assertions": {"evidence_gain": True, "offline_gold_overlap": True},
            }],
        }),
        "M45-P2C": signed({**common, "probe_id": "M45-P2C", "gate": "failed", "usage": {"embedding_provider_attempts": 0}}),
        "M45-P2D": signed({
            **common,
            "probe_id": "M45-P2D",
            "gate": "passed",
            "usage": {"embedding_provider_attempts": 0},
            "assertions": {"remaining_slots_supported": True},
        }),
        "M45-P3": signed({
            **common,
            "probe_id": "M45-P3",
            "gate": "failed",
            "usage": {"embedding_provider_attempts": 2},
            "scenarios": [
                {"scenario_id": "qst_0431", "gate": "failed", "execution": {"chosen_action": "stop"}},
                {"scenario_id": "qst_0461", "gate": "failed", "execution": {"chosen_action": "stop"}},
            ],
        }),
    }
    artifact = build_review_artifact(
        campaign=campaign,
        probe_payloads=probes,
        external_artifact_manifest={"sha256": "a" * 64},
    )
    assert artifact["qualification"]["decision"] == "review_required/no_go"
    assert artifact["qualification"]["provider_attempts"] == 8
    assert artifact["qualification"]["action_cards"] == {
        "query_rewrite_candidate": "completed",
        "context_expansion_candidate": "failed",
    }

    tampered = dict(artifact)
    tampered["qualification"] = dict(artifact["qualification"], decision="go_for_M46")
    with pytest.raises(RAGActionDiagnosticError):
        validate_review_artifact(tampered, campaign=campaign, probe_payloads=probes)


class _FakeProposalTransport:
    """模拟一次 Qwen JSON response，同时保留真实 adapter 所需的 usage 形状。"""

    model = "qwen3.7-plus"

    def __init__(self, response: dict[str, Any]) -> None:
        import json

        self._raw = json.dumps(response)
        self.request_count = 0
        self.total_tokens = 0
        self.last_prompt = ""

    def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str) -> str:
        assert node_purpose == PROPOSAL_PURPOSE
        assert system_prompt
        self.last_prompt = prompt
        self.request_count += 1
        self.total_tokens += 321
        return self._raw


def test_evidence_aware_proposal_keeps_only_locally_unsupported_slots() -> None:
    current = (_evidence(
        "fridge-current",
        "Kitchen cleanup notes mention opened items and a weekly tidy rota, but no agreed time.",
        run_id="proposal-run",
    ),)
    transport = _FakeProposalTransport({
        "requirements": [
            {
                "requirement_id": "opened_item_policy",
                "focused_query": "engineering kitchen fridge opened item cleanup policy",
                "support_marker_groups": [["opened items"], ["cleanup"]],
                "value_shape": "none",
            },
            {
                "requirement_id": "weekly_cleanup_schedule",
                "focused_query": "engineering kitchen fridge weekly cleanup schedule and timing",
                "support_marker_groups": [["weekly", "weekday"], ["cleanup", "tidy"]],
                "value_shape": "schedule",
            },
        ],
    })
    proposal = EvidenceAwareRequirementProposer(transport).propose(
        question=(
            "What is the proposed weekly cleanup schedule and routine for tidying the engineering "
            "kitchen fridge so old opened items get discarded?"
        ),
        current_evidence=current,
    )

    # 第一个 aspect 已由当前 Evidence 支持，必须由本地 coverage 丢弃；模型不能自己宣布缺口。
    assert [slot.identity for slot in proposal.slots] == ["weekly_cleanup_schedule"]
    assert proposal.usage.calls == 1
    assert proposal.usage.total_tokens == 321
    assert "title-fridge-current" not in transport.last_prompt
    assert "fridge-current" not in transport.last_prompt
    assert "[E1]" in transport.last_prompt
    assert "Each requirement must contain 1-5 support_marker_groups" in transport.last_prompt
    assert "each group must contain 1-4" in transport.last_prompt
    assert proposal.slots[0].marker_match_mode == "token_overlap"


@pytest.mark.parametrize(
    "row, reason",
    [
        (
            {
                "requirement_id": "rollback_threshold",
                "focused_query": "Serving Runtime rollback threshold 30%",
                "support_marker_groups": [["rollback"]],
                "value_shape": "numeric",
            },
            "proposal_focused_query_unsafe",
        ),
        (
            {
                "requirement_id": "rollback_steps",
                "focused_query": "Serving Runtime emergency rollback procedure",
                "support_marker_groups": [["rollback"]],
                "value_shape": "free_text",
            },
            "proposal_value_shape_invalid",
        ),
    ],
)
def test_structured_proposal_rejects_answer_values_and_unknown_shape(
    row: dict[str, Any], reason: str,
) -> None:
    transport = _FakeProposalTransport({"requirements": [row]})
    with pytest.raises(RequirementProposalError, match=reason):
        EvidenceAwareRequirementProposer(transport).propose(
            question="What is the Serving Runtime emergency rollback procedure?",
            current_evidence=(
                _evidence("rollback", "Serving Runtime rollback overview.", run_id="proposal-run"),
            ),
        )


def test_proposal_outbound_policy_is_exact_and_diagnostic_only() -> None:
    allowed = decide_outbound(
        OutboundRequest(
            receiver="qwen_chat",
            node_purpose=PROPOSAL_PURPOSE,
            data_class=PROPOSAL_DATA_CLASS,
            fields=frozenset({"prompt", "system_prompt", "model"}),
            fallback_available=False,
        ),
        policy=PROPOSAL_OUTBOUND_POLICY,
    )
    wrong_purpose = decide_outbound(
        OutboundRequest(
            receiver="qwen_chat",
            node_purpose="knowledge_answer_generation",
            data_class=PROPOSAL_DATA_CLASS,
            fields=frozenset({"prompt", "system_prompt", "model"}),
            fallback_available=False,
        ),
        policy=PROPOSAL_OUTBOUND_POLICY,
    )
    extra_field = decide_outbound(
        OutboundRequest(
            receiver="qwen_chat",
            node_purpose=PROPOSAL_PURPOSE,
            data_class=PROPOSAL_DATA_CLASS,
            fields=frozenset({"prompt", "system_prompt", "model", "document_key"}),
            fallback_available=False,
        ),
        policy=PROPOSAL_OUTBOUND_POLICY,
    )
    assert allowed.allowed
    assert not wrong_purpose.allowed
    assert not extra_field.allowed


def test_requirement_value_shapes_are_deterministic() -> None:
    schedule = RequirementSlot(
        "weekly_schedule",
        "engineering kitchen fridge weekly cleanup schedule",
        (("cleanup",),),
        value_shape="schedule",
    )
    steps = RequirementSlot(
        "dedicated_steps",
        "Serving Runtime Dedicated rollback procedure steps",
        (("dedicated",), ("rollback",)),
        value_shape="ordered_steps",
    )
    assert not schedule.supported_by_text("Weekly cleanup will be arranged later.")
    assert schedule.supported_by_text("Weekly cleanup happens Friday at 4 pm.")
    assert not steps.supported_by_text("Dedicated rollback has one high-level step.")
    assert steps.supported_by_text("Dedicated rollback:\n1. Pin the tag\n2. Redeploy and verify")


def test_proposal_token_overlap_matches_semantic_phrase_but_legacy_exact_does_not() -> None:
    target = "Cleanup procedure: Weekly Friday 4pm quick tidy and check the fridge."
    exact = RequirementSlot(
        "weekly_cleanup_schedule",
        "engineering kitchen fridge weekly cleanup schedule",
        (("weekly cleanup schedule", "fridge tidy rota", "cleaning routine"),),
        value_shape="schedule",
    )
    proposal = RequirementSlot(
        "weekly_cleanup_schedule",
        "engineering kitchen fridge weekly cleanup schedule",
        (("weekly cleanup schedule", "fridge tidy rota", "cleaning routine"),),
        value_shape="schedule",
        marker_match_mode="token_overlap",
    )
    assert not exact.supported_by_text(target)
    assert proposal.supported_by_text(target)
    assert exact.signature != proposal.signature


def test_proposal_coverage_does_not_stitch_schedule_across_unrelated_evidence() -> None:
    slot = RequirementSlot(
        "weekly_cleanup_schedule",
        "engineering kitchen fridge weekly cleanup schedule",
        (("weekly cleanup schedule", "fridge tidy rota", "cleaning routine"),),
        value_shape="schedule",
        marker_match_mode="token_overlap",
    )
    evidence = (
        _evidence("rota", "Weekly fridge tidy rota will be drafted.", run_id="proposal-run"),
        _evidence("unrelated", "The office is uncomfortable in the afternoon.", run_id="proposal-run"),
    )
    assert not slot.supported_by(evidence)
    assert slot.supported_by_text(
        "Weekly fridge tidy rota will be drafted. The cleanup is Friday at 4 pm."
    )


def test_proposal_marker_hint_keeps_relevant_seed_inside_two_seed_budget() -> None:
    slots = (
        RequirementSlot(
            "weekly_cleanup_schedule",
            "engineering kitchen fridge weekly cleanup schedule or rota details",
            (("weekly cleanup schedule", "fridge tidy rota", "cleaning routine"),),
            value_shape="schedule",
            marker_match_mode="token_overlap",
        ),
        RequirementSlot(
            "discard_policy_for_opened_items",
            "policy for discarding old opened items in engineering kitchen fridge",
            (("discard old opened items", "label opened jars with date", "expired items policy"),),
            value_shape="ordered_steps",
            marker_match_mode="token_overlap",
        ),
    )
    relevant = _evidence(
        "relevant",
        "Fridge tidy rota. Label opened jars with date; the full schedule is in the prior unit.",
        run_id="proposal-rank",
    )
    title_like = _evidence(
        "title-like",
        "Kitchen fridge cleanup policy schedule request with no agreed routine.",
        run_id="proposal-rank",
    )
    weekly_noise = _evidence(
        "weekly-noise",
        "Engineering kitchen fridge inventory has a weekly snapshot.",
        run_id="proposal-rank",
    )
    ranked = EnterpriseSiblingExpansionAdapter._rank_seeds(
        (relevant, title_like, weekly_noise), slots,
    )
    assert relevant in ranked[:2]


def test_validation_failure_retains_raw_only_on_exception_for_private_artifact() -> None:
    response = {
        "requirements": [{
            "requirement_id": "rollback_steps",
            "focused_query": "Serving Runtime emergency rollback procedure",
            "support_marker_groups": [["one", "two", "three", "four", "five"]],
            "value_shape": "ordered_steps",
        }],
    }
    proposer = EvidenceAwareRequirementProposer(_FakeProposalTransport(response))
    with pytest.raises(RequirementProposalError) as captured:
        proposer.propose(
            question="What is the Serving Runtime emergency rollback procedure?",
            current_evidence=(
                _evidence("rollback", "Serving Runtime rollback overview.", run_id="proposal-run"),
            ),
        )
    assert captured.value.reason_code == "proposal_marker_group_invalid"
    assert '"requirements"' in captured.value.raw_response
    assert "Current authorized evidence" in captured.value.prompt
    assert captured.value.usage is not None and captured.value.usage.calls == 1


def test_structured_proposal_to_existing_observation_to_expansion_vertical_slice() -> None:
    """M45-E 第一条 fake 纵向链：proposal 改写 requirement，但不重跑 initial retrieval。"""

    seed_coordinates = DocumentContextCoordinates("confluence", "doc-a", "physical-a", "seed", 0, 20)
    neighbor_coordinates = DocumentContextCoordinates(
        "confluence", "doc-a", "physical-a", "neighbor", 20, 40,
    )
    seed = _evidence(
        "enterprise-unit:seed",
        "Serving Runtime emergency rollback overview for Hosted and Dedicated fleets.",
        run_id="proposal-chain",
        coordinates=seed_coordinates,
    )
    neighbor_text = "Dedicated rollback redeploy sequence and post-rollback verification checklist."
    neighbor_metadata = replace(
        _entry("enterprise-unit:neighbor", ""),
        source_kind="confluence",
        source_key="physical-a",
        data_class="public_benchmark_document",
        purposes=("answer_evidence", "generation_context"),
        content_identity=_entry("x", neighbor_text).content_identity,
    )
    neighbor_content = replace(neighbor_metadata, content=neighbor_text)
    runtime = SimpleNamespace(
        bundle=SimpleNamespace(release_identity="profile-m45", entries=(neighbor_metadata,)),
        context_loader=_FakeContextLoader({"neighbor": (neighbor_content, neighbor_coordinates)}),
        manifest=SimpleNamespace(profile_identity="profile-m45", unit_recipe_identity="unit-recipe-m45"),
    )
    proposer = EvidenceAwareRequirementProposer(_FakeProposalTransport({
        "requirements": [{
            "requirement_id": "dedicated_completion_checklist",
            "focused_query": "Serving Runtime Dedicated rollback redeploy verification checklist",
            "support_marker_groups": [["dedicated"], ["redeploy"], ["verification"]],
            "value_shape": "none",
        }],
    }))
    proposal = proposer.propose(
        question="What is the Serving Runtime emergency rollback procedure for Hosted and Dedicated?",
        current_evidence=(seed,),
    )
    adapter = EnterpriseSiblingExpansionAdapter(runtime)  # type: ignore[arg-type]
    diagnostic = RAGRecoveryDiagnostic()
    observation = diagnostic.observe_existing(
        scenario_id="qst_0431",
        runtime_scope="external_profile",
        slots=proposal.slots,
        initial=_outcome(seed),
        request=_request(),
        expansion_adapter=adapter,
    )
    result = diagnostic.execute(
        observation=observation,
        slots=proposal.slots,
        tool=_FakeTool({}),
        request=_request(),
        expansion_adapter=adapter,
    )
    assert observation.eligible_actions == ("context_expansion_candidate", "stop")
    assert result.evidence_delta.gained
    assert result.consumed.retrieval_batches == 0
    assert all(slot.supported_by((seed,) + result.added_evidence) for slot in proposal.slots)
    assert "prompt" not in proposal.safe_projection()
    assert proposal.private_projection()["prompt"]


def test_reopened_review_requires_old_no_go_and_two_p4_expansion_passes() -> None:
    campaign = load_reopened_diagnostic_campaign()
    predecessor = json.loads(
        Path("eval/reports/m45/m45-b3-diagnostic-review.json").read_text(encoding="utf-8")
    )
    source_identity = predecessor["probe_lineage"]["M45-P3"]["artifact_identity"]
    scenario = lambda scenario_id: {
        "scenario_id": scenario_id,
        "proposal_status": "completed",
        "proposal": {
            "schema_version": "phase4b-m45-rag-requirement-proposal-v1",
            "prompt_fingerprint": f"prompt-{scenario_id}",
            "response_fingerprint": f"response-{scenario_id}",
        },
        "execution": {"chosen_action": "context_expansion_candidate"},
        "assertions": {"proposal_gaps_supported": True},
        "gate": "passed",
        "decision": "continue",
    }
    p4: dict[str, Any] = {
        "schema_version": "phase4b-m45-live-probe-v2",
        "probe_id": "M45-P4",
        "classification": "exploratory",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "predecessor_campaign_identity": campaign.predecessor_campaign_identity,
        "source_artifact_identity": source_identity,
        "executed_at": "2026-08-25T00:00:00+00:00",
        "scenarios": [scenario("qst_0431"), scenario("qst_0461")],
        "gate": "passed",
        "decision": "continue",
        "usage": {
            "retrieval_calls": 0,
            "embedding_provider_attempts": 0,
            "chat_model_calls": 2,
            "composer_calls": 0,
            "observed_chat_tokens": 2400,
            "token_usage_observed": True,
        },
        "budget_respected": True,
        "reserve_access_state": "sealed",
    }
    p4["artifact_identity"] = canonical_hash(p4)
    artifact = build_reopened_review_artifact(
        campaign=campaign,
        predecessor_review=predecessor,
        p4_payload=p4,
        external_artifact_manifest={"sha256": "a" * 64},
    )
    assert artifact["qualification"]["decision"] == "go_for_M46"
    assert artifact["qualification"]["provider_attempts"] == {
        "embedding": 8, "chat": 2, "total": 10,
    }

    tampered = dict(artifact)
    tampered["qualification"] = dict(artifact["qualification"], decision="review_required/no_go")
    with pytest.raises(RAGActionDiagnosticError):
        validate_reopened_review_artifact(
            tampered,
            campaign=campaign,
            predecessor_review=predecessor,
            p4_payload=p4,
        )


def test_repair_review_preserves_incomplete_p4r_as_no_go() -> None:
    """★ 已消耗的真实调用不能因 runner 丢证据而被记成零次或假装通过。"""

    campaign = load_repair_diagnostic_campaign()
    predecessor = json.loads(
        Path("eval/reports/m45/m45-b3-reopened-review.json").read_text(encoding="utf-8")
    )
    p4r = json.loads(
        Path(".agent_work/temp/m45-p4r-recovered.json").read_text(encoding="utf-8")
    )
    artifact = build_repair_review_artifact(
        campaign=campaign,
        predecessor_review=predecessor,
        p4r_payload=p4r,
        external_artifact_manifest={"sha256": "b" * 64},
    )

    qualification = artifact["qualification"]
    assert qualification["decision"] == "review_required/no_go"
    assert qualification["required_checks"]["qst_0461_offline_expansion_passed"] is True
    assert qualification["required_checks"]["qst_0431_revalidation_expansion_passed"] is False
    assert qualification["provider_attempts"] == {
        "embedding": 8, "chat": 3, "total": 11,
    }
    assert qualification["repair_observed_chat_tokens"] is None
    assert qualification["token_usage_observed"] is False
    assert qualification["failure_reason_codes"] == [
        "proposal_no_unsupported_requirement:qst_0431",
        "p4r_token_usage_not_observed",
        "p4r_failure_artifact_incomplete",
    ]

    tampered = dict(artifact)
    tampered["qualification"] = dict(qualification, decision="go_for_M46")
    with pytest.raises(RAGActionDiagnosticError):
        validate_repair_review_artifact(
            tampered,
            campaign=campaign,
            predecessor_review=predecessor,
            p4r_payload=p4r,
        )


def test_continuation_review_turns_two_action_cards_green_without_new_provider() -> None:
    campaign = load_continuation_diagnostic_campaign()
    predecessor = json.loads(
        Path("eval/reports/m45/m45-b3-repair-review.json").read_text(encoding="utf-8")
    )
    p5 = json.loads(Path(".agent_work/temp/m45-p5-first.json").read_text(encoding="utf-8"))
    artifact = build_continuation_review_artifact(
        campaign=campaign,
        predecessor_review=predecessor,
        p5_payload=p5,
        external_artifact_manifest={"sha256": "c" * 64},
    )
    qualification = artifact["qualification"]
    assert qualification["decision"] == "go_for_M46"
    assert qualification["action_cards"] == {
        "query_rewrite_candidate": "completed",
        "context_expansion_candidate": "completed",
    }
    assert qualification["provider_attempts"] == {
        "embedding": 8, "chat": 3, "total": 11,
    }
    assert qualification["p5_provider_attempts"] == 0
    assert qualification["failure_reason_codes"] == []

    tampered = dict(artifact)
    tampered["qualification"] = dict(qualification, decision="review_required/no_go")
    with pytest.raises(RAGActionDiagnosticError):
        validate_continuation_review_artifact(
            tampered,
            campaign=campaign,
            predecessor_review=predecessor,
            p5_payload=p5,
        )
