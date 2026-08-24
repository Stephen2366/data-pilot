"""M44-A/B：B2 bundle、父预算与 closed-world runtime resolver。"""

from __future__ import annotations

from dataclasses import replace
import json

import pytest

from engine.governance import demo_caller
from engine.phase4b.b2_contracts import load_b2_contract_bundle
from engine.phase4b.knowledge_runtime import (
    KnowledgeRuntimeResolutionError,
    KnowledgeRuntimeResolver,
    KnowledgeRuntimeSpec,
)
from engine.phase4b.loop_contracts import BudgetLedger, BudgetProfile, EvidenceRequirement, ResourceConsumption
from engine.governance import OutboundRequest, decide_outbound
from engine.harness.adapters import _sql_observation
from engine.harness.contracts import HarnessRequest
from engine.nl2sql.generator import generate_sql_repair_from_plan_step
from engine.nl2sql.llm_call import execute_llm_call
from engine.nl2sql.pipeline import SQLRepairContext
from engine.nl2sql.planner import QueryPlanStep
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.objects import SchemaGraph
from engine.tools.sql_tool import SQLToolResult


def test_b2_bundle_binds_b1_and_exact_option_a_budget() -> None:
    bundle = load_b2_contract_bundle()
    assert bundle.contract_version == "phase4b-b2-contracts-v1"
    assert bundle.payload["task_state_version"] == "phase4b-task-state-v2"
    assert bundle.payload["budget_profile"] == {
        "identity": "phase4b-b2-parent-budget-conservative-v1",
        "max_actions": 3,
        "max_deep_tools": 3,
        "max_sql_actions": 3,
        "max_knowledge_actions": 1,
        "max_repairs_per_requirement": 1,
        "max_retrieval_batches": 1,
        "max_candidates": 5,
        "max_selected": 3,
        "max_generation_visible": 3,
        "max_model_calls": 6,
        "max_total_tokens": 24000,
    }


def test_budget_checks_before_action_and_reconciles_unknown_tokens() -> None:
    profile = BudgetProfile(**load_b2_contract_bundle().payload["budget_profile"])
    ledger = BudgetLedger(profile)
    actual = ResourceConsumption(actions=1, deep_tools=1, sql_actions=1, token_usage_observed=False)
    ledger = ledger.consume(actual)
    assert ledger.consumed.total_tokens == 0
    assert ledger.consumed.token_usage_observed is False
    assert not ledger.allows(ResourceConsumption(actions=3, deep_tools=3))
    assert not ledger.allows(
        ResourceConsumption(actions=1, deep_tools=1, repairs=1),
        repair_count_for_requirement=1,
    )


def test_runtime_resolver_uses_typed_scope_and_never_falls_back() -> None:
    class Sentinel:
        def run_for_hybrid(self, *_args: object, **_kwargs: object) -> object:
            return object()

    sentinel = Sentinel()
    resolver = KnowledgeRuntimeResolver((
        KnowledgeRuntimeSpec("business_release", lambda: sentinel, "business-v1"),  # type: ignore[arg-type]
    ))
    requirement = EvidenceRequirement(
        "doc:policy", "document", "policy", "退款政策", runtime_scope="business_release"
    )
    resolved = resolver.resolve(requirement=requirement, caller=demo_caller(caller_id="m44", roles=("ops",)))
    assert resolved.adapter is sentinel
    assert resolved.safe_projection() == {"scope": "business_release", "runtime_identity": "business-v1"}

    with pytest.raises(KnowledgeRuntimeResolutionError, match="knowledge_runtime_unavailable"):
        resolver.resolve(
            requirement=replace(requirement, runtime_scope="external_profile"),
            caller=demo_caller(caller_id="m44", roles=("ops",)),
        )
    with pytest.raises(KnowledgeRuntimeResolutionError, match="caller_untrusted"):
        resolver.resolve(requirement=requirement, caller=None)
    unavailable = KnowledgeRuntimeResolver((
        KnowledgeRuntimeSpec("business_release", lambda: None, "business-missing"),  # type: ignore[arg-type]
    ))
    with pytest.raises(KnowledgeRuntimeResolutionError, match="knowledge_runtime_unavailable"):
        unavailable.resolve(requirement=requirement, caller=demo_caller(caller_id="m44", roles=("ops",)))


def test_requirement_and_registry_are_closed_world() -> None:
    with pytest.raises(ValueError):
        EvidenceRequirement("x", "document", "p", "q", runtime_scope="not_applicable")
    with pytest.raises(ValueError, match="knowledge_runtime_registry_invalid"):
        KnowledgeRuntimeResolver((
            KnowledgeRuntimeSpec("business_release", lambda: object(), "one"),  # type: ignore[arg-type]
            KnowledgeRuntimeSpec("business_release", lambda: object(), "two"),  # type: ignore[arg-type]
        ))


def test_sql_repair_has_independent_outbound_purpose_and_minimal_context() -> None:
    request = OutboundRequest(
        receiver="qwen_chat", node_purpose="sql_repair", data_class="text2sql_prompt",
        fields=frozenset({"prompt", "system_prompt", "model"}), fallback_available=False,
    )
    assert decide_outbound(request).allowed
    assert not decide_outbound(replace(request, node_purpose="sql_repair_other")).allowed
    assert not decide_outbound(replace(request, fields=frozenset({"prompt", "system_prompt", "model", "rows"}))).allowed

    with pytest.raises(ValueError, match="sql_repair_issue_not_allowed"):
        SQLRepairContext(candidate_sql="SELECT 1", issue_code="generic_db_error")


def test_repair_generator_uses_typed_issue_and_sql_observation_only_classifies_date_trunc() -> None:
    class Client:
        provider_label = "fixture"
        model = "fixture"

        def __init__(self) -> None:
            self.purpose = ""
            self.prompt = ""

        def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str = "") -> str:
            self.purpose, self.prompt = node_purpose, prompt
            return json.dumps({"sql": "SELECT DATE_FORMAT(paid_at, '%Y-%m-01') AS month FROM orders"})

    step = QueryPlanStep(
        step_id="s1", step_index=1, step_type="sql_query", purpose="按月查询", task_type="aggregation",
        tables=["orders"], columns=["orders.paid_at"], group_by=["orders.paid_at"],
        output_columns=["month"], output_expressions={"month": "orders.paid_at"},
    )
    graph = SchemaGraph(
        tables=["orders"], fields={"orders": ["paid_at"]}, metrics=[], relations=[], join_paths=[]
    )
    client = Client()
    repaired = generate_sql_repair_from_plan_step(
        question="按月查询订单", user_role="ops", plan_step=step, schema_graph=graph,
        domain_schema=load_domain_schema(), candidate_sql="SELECT DATE_TRUNC('month', paid_at) FROM orders",
        issue_code="mysql_unsupported_date_trunc", llm_client=client,
    )
    assert client.purpose == "sql_repair" and "mysql_unsupported_date_trunc" in client.prompt
    assert "raw db error" not in client.prompt.lower()
    assert "DATE_FORMAT" in repaired.sql

    harness_request = HarnessRequest(
        question="按月查询订单", run_id="m44-dialect", caller=demo_caller(caller_id="m44", roles=("ops",)),
        active_sql_role="ops",
    )
    dialect = _sql_observation(
        request=harness_request, sql="SELECT DATE_TRUNC('month', paid_at) FROM orders",
        answer_hint="", tool_result=SQLToolResult(error_type="sql_execution_error"),
        error_type="sql_execution_error", message="private db text",
    )
    generic = _sql_observation(
        request=harness_request, sql="SELECT unknown_fn(paid_at) FROM orders",
        answer_hint="", tool_result=SQLToolResult(error_type="sql_execution_error"),
        error_type="sql_execution_error", message="private db text",
    )
    assert dialect.reason_code == "sql_dialect_incompatible"
    assert dialect.diagnostics["issue_code"] == "mysql_unsupported_date_trunc"
    assert generic.reason_code == "sql_execution_error" and "issue_code" not in generic.diagnostics


def test_llm_usage_is_per_call_delta_and_unknown_fake_is_not_observed() -> None:
    class Metered:
        provider_label = "fixture"
        model = "fixture"
        request_count = 4
        prompt_tokens = 100
        completion_tokens = 50
        total_tokens = 150

        def complete(self, **_kwargs: object) -> str:
            self.request_count += 1
            self.prompt_tokens += 10
            self.completion_tokens += 5
            self.total_tokens += 15
            return "ok"

    metered = execute_llm_call(Metered(), prompt="p", system_prompt="s", stage="sql_generation")
    assert metered.evidence.usage == {
        "observed": True, "request_count": 1, "prompt_tokens": 10,
        "completion_tokens": 5, "total_tokens": 15,
    }

    class Unknown:
        def complete(self, **_kwargs: object) -> str:
            return "ok"

    unknown = execute_llm_call(Unknown(), prompt="p", system_prompt="s", stage="sql_generation")
    assert unknown.evidence.usage == {"observed": False}
