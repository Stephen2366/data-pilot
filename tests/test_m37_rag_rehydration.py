"""M37 窄 B：业务 Document rehydrate 与强制 reacquisition 合同。"""

from __future__ import annotations

from dataclasses import replace

from engine.governance import test_caller as make_test_caller
from engine.harness.adapters import RAGToolAdapter
from engine.harness.contracts import HarnessRequest
from engine.harness.graph import HarnessRuntime
from engine.harness.thread import ThreadCheckpointManager
from engine.harness.turn import TurnRequest, run_turn
from engine.rag.answer_flow import AnswerEvidenceRequirement, RAGAnswerFlow, RAGAnswerRequest
from engine.rag.knowledge_tool import KnowledgeTool
from engine.rag.release import load_active_release
from engine.rag.retrieval import RetrievalBudget


def _request(
    *,
    run_id: str,
    refs=(),
    equivalent: bool = False,
    runtime_kind: str = "business_release",
    requirement: AnswerEvidenceRequirement | None = None,
) -> RAGAnswerRequest:
    """集中构造业务/external 两种 runtime 的 Evidence validity 请求。"""

    return RAGAnswerRequest(
        question="质量问题退款需要提供哪些材料？",
        caller=make_test_caller(caller_id="m37-rag", roles={"customer_service"}),
        run_id=run_id,
        requirement=requirement or AnswerEvidenceRequirement(max_claims=2),
        retrieval_budget=RetrievalBudget(max_candidates=5, max_selected=2),
        prior_evidence_refs=tuple(refs),
        requirement_equivalent=equivalent,
        knowledge_runtime_kind=runtime_kind,  # type: ignore[arg-type]
    )


def test_equivalent_business_follow_up_rehydrates_without_retrieval_and_mints_new_ids() -> None:
    """同 active identity 仍重新授权、过 Gate，并生成新 run ledger/citation。"""

    flow = RAGAnswerFlow()
    first = flow.run(_request(run_id="first"))
    refs = tuple(item.ref for item in first.ledger.evidence)
    followed = flow.run(_request(run_id="follow", refs=refs, equivalent=True))

    assert first.answer_status == followed.answer_status == "complete"
    assert followed.diagnostics.knowledge_tool_calls == 0
    assert followed.evidence_validity["decision"] == "rehydrated"
    assert followed.evidence_validity["old_new_relation"] == "unchanged_current"
    assert {item.ref.evidence_id for item in first.ledger.evidence}.isdisjoint(
        {item.ref.evidence_id for item in followed.ledger.evidence}
    )
    assert {item.citation_id for item in first.citations}.isdisjoint(
        {item.citation_id for item in followed.citations}
    )
    assert all(item.ref.run_id == "follow" for item in followed.ledger.evidence)


def test_requirement_change_and_external_runtime_each_retrieve_exactly_once() -> None:
    """非等价 action 与 external profile 永远不进入业务 rehydrate seam。"""

    flow = RAGAnswerFlow()
    first = flow.run(_request(run_id="first"))
    refs = tuple(item.ref for item in first.ledger.evidence)

    changed = flow.run(_request(run_id="changed", refs=refs, equivalent=False))
    external = flow.run(
        _request(run_id="external", refs=refs, equivalent=True, runtime_kind="external_profile")
    )

    assert changed.diagnostics.knowledge_tool_calls == 1
    assert changed.evidence_validity["reason"] == "requirement_changed"
    assert external.diagnostics.knowledge_tool_calls == 1
    assert external.evidence_validity["reason"] == "external_profile_always_retrieves"


def test_changed_identity_reacquires_current_evidence_instead_of_using_old_body() -> None:
    """active 内容变化后旧 ref 不再可重水化，只允许一次 Knowledge Tool 取当前版本。"""

    first = RAGAnswerFlow().run(_request(run_id="first"))
    refs = tuple(item.ref for item in first.ledger.evidence)
    pointer, bundle = load_active_release()
    changed_entries = tuple(
        replace(
            entry,
            content=entry.content + "\n当前版本补充说明。",
            content_identity=entry.content_identity + "-m37",
        )
        if entry.authority_ref in {ref.authority_identity for ref in refs}
        else entry
        for entry in bundle.entries
    )
    changed_bundle = replace(bundle, release_identity=bundle.release_identity + "-m37", entries=changed_entries)
    loader = lambda: (pointer, changed_bundle)
    flow = RAGAnswerFlow(knowledge_tool=KnowledgeTool(active_loader=loader), active_loader=loader)

    followed = flow.run(_request(run_id="changed", refs=refs, equivalent=True))

    assert followed.answer_status == "complete"
    assert followed.diagnostics.knowledge_tool_calls == 1
    assert followed.evidence_validity["reason"] == "document_identity_changed"
    assert all(item.ref.content_identity.endswith("-m37") for item in followed.ledger.evidence)


def test_reauthorization_denial_stops_without_retrieval_or_identity_leak() -> None:
    """ACL 变化直接安全停止，不能靠 retrieval 旁路重新发现同一文档。"""

    first = RAGAnswerFlow().run(_request(run_id="first"))
    refs = tuple(item.ref for item in first.ledger.evidence)
    pointer, bundle = load_active_release()
    denied_entries = tuple(
        replace(entry, public=False, allowed_roles=frozenset({"admin"}))
        if entry.authority_ref in {ref.authority_identity for ref in refs}
        else entry
        for entry in bundle.entries
    )
    denied_bundle = replace(bundle, entries=denied_entries)
    loader = lambda: (pointer, denied_bundle)
    flow = RAGAnswerFlow(knowledge_tool=KnowledgeTool(active_loader=loader), active_loader=loader)

    denied = flow.run(_request(run_id="denied", refs=refs, equivalent=True))

    assert (denied.answer_status, denied.safety_status, denied.reason_code) == (
        "no_answer", "blocked", "document_acl_denied"
    )
    assert denied.diagnostics.knowledge_tool_calls == 0
    assert denied.evidence_validity["decision"] == "denied"
    projection = str(denied.safe_projection())
    assert all(ref.authority_identity not in projection for ref in refs)


def test_real_turn_adapter_rehydrates_and_applies_server_selected_explanation_style() -> None:
    """端到端 turn 使用当前 requirement、新 run citation 和确定性解释样式。"""

    class NeverSQL:
        """端到端 RAG 场景的反向哨兵：误路由到 SQL 就立即失败。"""

        def run(self, _request):
            """拒绝任何 SQL 调用。"""

            raise AssertionError("RAG follow-up 不得调用 SQL")

    caller = make_test_caller(caller_id="m37-turn", roles={"customer_service"})
    manager = ThreadCheckpointManager()
    runtime = HarnessRuntime(sql_tool=NeverSQL(), rag_tool=RAGToolAdapter())
    initial = run_turn(
        request=TurnRequest(
            HarnessRequest(
                question="质量问题退款规则如何处理？",
                run_id="turn-initial",
                caller=caller,
                active_sql_role="customer_service",
                enable_bounded_follow_up=True,
            )
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert initial.thread is not None
    followed = run_turn(
        request=TurnRequest(
            HarnessRequest(
                question="执行追问",
                run_id="turn-follow",
                caller=caller,
                active_sql_role="customer_service",
            ),
            thread_id=initial.thread.thread_id,
            expected_version=initial.thread.checkpoint_version,
            follow_up_action="explain_same_evidence",
            follow_up_fields={"style": "通俗说明"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )

    observation = followed.result.observation
    assert observation is not None and followed.result.answer.startswith("通俗说明：")
    assert observation.diagnostics["knowledge_tool_calls"] == 0
    validity = observation.diagnostics["evidence_validity"]
    assert validity["decision"] == "rehydrated"
    assert validity["previous_requirement_identity"] == validity["current_requirement_identity"]
