"""M42-C 最小 caller、gold-first business retrieval 与 Hybrid legacy 隔离。"""

from __future__ import annotations

from engine.governance import test_caller as make_test_caller
from engine.harness.contracts import HarnessRequest
from engine.harness.router import DeterministicRouter
from engine.phase4b.caller import Phase4BFixtureCallerResolver
from engine.phase4b.contracts import load_b0_contract_bundle
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool


QUESTION = "如果最近质量问题退款明显增多，客服受理这类退款时可以直接按全额退款处理吗？需要哪些前提和材料？"


def test_minimal_phase4b_caller_has_dual_resolved_roles_but_only_ops_is_active() -> None:
    resolver = Phase4BFixtureCallerResolver(fixture_kind="test")
    resolution = resolver.resolve("ops")
    assert resolution is not None
    assert resolution.active_sql_role == "ops"
    assert resolution.caller.resolved_roles == frozenset({"ops", "customer_service"})
    assert resolution.caller.tenant_id == "phase4b-demo-tenant"
    assert resolver.resolve("customer_service") is None
    assert resolver.resolve("admin") is None


def test_gold_first_question_uses_default_budget_and_requires_customer_service_acl() -> None:
    """正向 caller 能检索；缺客服角色时在授权层看不到受限政策。"""

    resolution = Phase4BFixtureCallerResolver(fixture_kind="test").resolve("ops")
    assert resolution is not None
    outcome = KnowledgeTool().retrieve(
        KnowledgeRequest(
            question=QUESTION,
            caller=resolution.caller,
            purpose="answer_evidence",
            run_id="m42-business-observation-test",
        )
    )
    assert outcome.diagnostics.adapter_calls == 1
    assert outcome.reason_code in {"evidence_retrieved", "no_candidate"}

    ops_only = KnowledgeTool().retrieve(
        KnowledgeRequest(
            question=QUESTION,
            caller=make_test_caller(caller_id="ops-only", roles={"ops"}),
            purpose="answer_evidence",
            run_id="m42-business-observation-denied",
        )
    )
    selected_keys = {item.payload.document_key for item in ops_only.selected_evidence}
    assert not {"refund_policy_basic", "refund_policy_quality"} & selected_keys


def test_new_hybrid_operator_is_contract_only_and_legacy_router_is_unchanged() -> None:
    bundle = load_b0_contract_bundle()
    assert bundle.payload["hybrid_operator"]["operator"] == "refund_change_and_policy"
    assert bundle.payload["hybrid_operator"]["status"] == "contract_only"

    resolution = Phase4BFixtureCallerResolver(fixture_kind="test").resolve("ops")
    assert resolution is not None
    legacy = DeterministicRouter().decide(
        HarnessRequest(
            question="退款原因以及政策和材料是什么？",
            run_id="m42-legacy-hybrid",
            caller=resolution.caller,
            active_sql_role="ops",
        )
    )
    assert legacy.hybrid_plan is not None
    assert legacy.hybrid_plan.operator == "refund_reason_and_policy"
    assert legacy.hybrid_plan.identity == "hybrid-refund-reason-and-policy-v1"
