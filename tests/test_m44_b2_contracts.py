"""M44-A/B：B2 bundle、父预算与 closed-world runtime resolver。"""

from __future__ import annotations

from dataclasses import replace
import json

import pytest
import sqlglot

from app.schemas.agent import ToolCallTrace
import engine.phase4b.agent_loop as agent_loop_module
from engine.governance import demo_caller
from engine.phase4b.b2_contracts import load_b2_contract_bundle
from engine.phase4b.knowledge_runtime import (
    KnowledgeRuntimeResolutionError,
    KnowledgeRuntimeResolver,
    KnowledgeRuntimeSpec,
)
from engine.phase4b.loop_contracts import BudgetLedger, BudgetProfile, EvidenceRequirement, ResourceConsumption
from engine.governance import OutboundRequest, decide_outbound
from engine.harness.adapters import Text2SQLToolAdapter, _sql_observation
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.nl2sql.generator import GeneratedSQL, generate_sql_repair_from_plan_step
from engine.nl2sql.llm_call import execute_llm_call
import engine.nl2sql.pipeline as pipeline_module
from engine.nl2sql.pipeline import SQLRepairContext, run_text2sql_pipeline
from engine.nl2sql.planner import QueryPlan, QueryPlanStep
from engine.nl2sql.schema_loader import load_domain_schema
from engine.nl2sql.sql_repair import (
    SQLRepairSnapshot,
    repair_sql_candidate,
    validate_sql_repair_strategy,
)
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
        SQLRepairContext(
            candidate_sql="SELECT 1",
            issue_code="generic_db_error",
            plan_step=QueryPlanStep(
                step_id="s1", step_index=1, step_type="sql_query", purpose="测试",
                task_type="lookup", tables=["orders"], output_columns=["value"],
            ),
        )


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
    assert "必须保留的输出列" not in client.prompt
    assert "DATE_FORMAT" in repaired.sql

    harness_request = HarnessRequest(
        question="按月查询订单", run_id="m44-dialect", caller=demo_caller(caller_id="m44", roles=("ops",)),
        active_sql_role="ops",
    )
    dialect = _sql_observation(
        request=harness_request, sql="SELECT DATE_TRUNC('month', paid_at) FROM orders",
        answer_hint="", tool_result=SQLToolResult(
            error_type="sql_execution_error",
            issue_code="mysql_unsupported_date_trunc",
        ),
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


def test_deterministic_ast_repair_preserves_full_projection_without_repair_provider() -> None:
    """候选 A 只编译 dialect AST，不能重新生成并漏掉 diff/change_rate。"""

    class MustNotCall:
        def complete(self, **_kwargs: object) -> str:
            raise AssertionError("deterministic repair must not call provider")

    step = QueryPlanStep(
        step_id="s1", step_index=1, step_type="sql_query", purpose="比较两月退款",
        task_type="aggregation", tables=["refunds"],
        columns=["refunds.processed_at", "refunds.refund_amount"],
        group_by=["DATE_TRUNC('month', refunds.processed_at)"], order_by=["month ASC"],
        output_columns=["month", "net_refund_amount", "diff", "change_rate"],
    )
    graph = SchemaGraph(
        tables=["refunds"], fields={"refunds": ["processed_at", "refund_amount"]},
        metrics=["net_refund_amount"], relations=[], join_paths=[],
    )
    candidate = """
        WITH monthly AS (
          SELECT DATE_TRUNC('month', refunds.processed_at) AS month,
                 SUM(refunds.refund_amount) AS net_refund_amount
          FROM refunds GROUP BY DATE_TRUNC('month', refunds.processed_at)
        )
        SELECT month, net_refund_amount,
               net_refund_amount - LAG(net_refund_amount) OVER (ORDER BY month) AS diff,
               (net_refund_amount - LAG(net_refund_amount) OVER (ORDER BY month))
                 / NULLIF(LAG(net_refund_amount) OVER (ORDER BY month), 0) AS change_rate
        FROM monthly ORDER BY month ASC
    """
    repaired = repair_sql_candidate(
        strategy="deterministic_ast", question="比较七八月", user_role="ops",
        plan_step=step, schema_graph=graph, domain_schema=load_domain_schema(),
        candidate_sql=candidate, issue_code="mysql_unsupported_date_trunc",
        llm_client=MustNotCall(),
    )
    parsed = sqlglot.parse_one(repaired.sql, read="mysql")
    assert [item.alias_or_name for item in parsed.expressions] == [
        "month", "net_refund_amount", "diff", "change_rate",
    ]
    assert "DATE_TRUNC" not in repaired.sql.upper()
    assert "STR_TO_DATE" in repaired.sql.upper()


def test_enriched_llm_repair_only_adds_trusted_required_output_aliases() -> None:
    """候选 B 增加 output contract，但不把 Schema 或数据库错误带进 prompt。"""

    class Client:
        provider_label = "fixture"
        model = "fixture"

        def __init__(self) -> None:
            self.prompt = ""

        def complete(self, *, prompt: str, **_kwargs: object) -> str:
            self.prompt = prompt
            return json.dumps({
                "sql": (
                    "SELECT DATE_FORMAT(processed_at, '%Y-%m-01') AS month, "
                    "SUM(refund_amount) AS net_refund_amount, 1 AS diff, 1 AS change_rate "
                    "FROM refunds GROUP BY DATE_FORMAT(processed_at, '%Y-%m-01')"
                )
            })

    step = QueryPlanStep(
        step_id="s1", step_index=1, step_type="sql_query", purpose="比较两月退款",
        task_type="aggregation", tables=["refunds"], columns=["refunds.processed_at"],
        output_columns=["month", "net_refund_amount", "diff", "change_rate"],
    )
    graph = SchemaGraph(
        tables=["refunds"], fields={"refunds": ["processed_at"]},
        metrics=[], relations=[], join_paths=[],
    )
    client = Client()
    repair_sql_candidate(
        strategy="llm_enriched", question="比较七八月", user_role="ops",
        plan_step=step, schema_graph=graph, domain_schema=load_domain_schema(),
        candidate_sql="SELECT DATE_TRUNC('month', processed_at) AS month FROM refunds",
        issue_code="mysql_unsupported_date_trunc", llm_client=client,
    )
    assert '必须保留的输出列（名称与顺序）：["month", "net_refund_amount", "diff", "change_rate"]' in client.prompt
    assert "raw db error" not in client.prompt.lower()
    assert "join_paths" not in client.prompt and "refunds.refund_amount" not in client.prompt


def test_sql_repair_strategy_is_server_side_closed_world() -> None:
    assert validate_sql_repair_strategy("llm_minimal") == "llm_minimal"
    assert Text2SQLToolAdapter(db=object())._repair_strategy == "deterministic_ast"  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="sql_repair_strategy_not_allowed"):
        validate_sql_repair_strategy("client_selected")
    with pytest.raises(ValueError, match="sql_repair_strategy_not_allowed"):
        Text2SQLToolAdapter(db=object(), repair_strategy="client_selected")  # type: ignore[arg-type]


def _month_repair_snapshot(*, output_columns: list[str] | None = None) -> SQLRepairSnapshot:
    columns = output_columns or ["month"]
    return SQLRepairSnapshot(
        candidate_sql=(
            "SELECT DATE_TRUNC('month', refunds.processed_at) AS month "
            "FROM refunds GROUP BY DATE_TRUNC('month', refunds.processed_at) ORDER BY month ASC"
        ),
        issue_code="mysql_unsupported_date_trunc",
        plan_step=QueryPlanStep(
            step_id="repair-step", step_index=1, step_type="sql_query", purpose="按月查询退款",
            task_type="aggregation", tables=["refunds"], columns=["refunds.processed_at"],
            group_by=["DATE_TRUNC('month', refunds.processed_at)"], order_by=["month ASC"],
            output_columns=columns,
            output_expressions={"month": "DATE_TRUNC('month', refunds.processed_at)"},
        ),
    )


def test_repair_pipeline_reuses_original_plan_without_query_plan_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """缩小版 A：repair 只重验原计划，默认 AST 路径的 provider call 为零。"""

    class MustNotCall:
        def complete(self, **_kwargs: object) -> str:
            raise AssertionError("deterministic repair must not call provider")

    def fail_replan(**_kwargs: object) -> object:
        raise AssertionError("repair must not generate a second QueryPlan")

    def execute_repaired(**kwargs: object) -> SQLToolResult:
        assert "DATE_TRUNC" not in str(kwargs["sql"]).upper()
        return SQLToolResult(
            columns=["month"], rows=[{"month": "2026-07-01"}], tables_used=["refunds"]
        )

    monkeypatch.setattr(pipeline_module, "get_default_llm_client", lambda: MustNotCall())
    monkeypatch.setattr(pipeline_module, "generate_query_plan", fail_replan)
    monkeypatch.setattr(pipeline_module, "run_sql_tool", execute_repaired)
    result = run_text2sql_pipeline(
        question="按月查询退款", user_role="ops", db=object(), trace_id="repair-reuse",
        repair_context=_month_repair_snapshot(),
    )
    assert result.error_type is None and result.tool_result is not None
    plan_trace = next(step for step in result.trace_steps if step.name == "query_plan")
    repair_trace = next(step for step in result.trace_steps if step.name == "sql_repair")
    assert plan_trace.metadata["repair_plan_reused"] is True
    assert "llm_call" not in plan_trace.metadata
    assert repair_trace.metadata["repair_strategy"] == "deterministic_ast"
    assert repair_trace.metadata["query_plan_step"]["output_columns"] == ["month"]
    assert "llm_call" not in repair_trace.metadata


def test_initial_dialect_failure_issues_private_snapshot_from_validated_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次失败把同一 plan/candidate 私下交给 Loop，公开 action 投影看不到 snapshot。"""

    snapshot_plan = _month_repair_snapshot().plan_step
    candidate = _month_repair_snapshot().candidate_sql

    monkeypatch.setattr(pipeline_module, "get_default_llm_client", lambda: object())
    monkeypatch.setattr(
        pipeline_module, "generate_query_plan", lambda **_kwargs: QueryPlan(steps=[snapshot_plan])
    )
    monkeypatch.setattr(
        pipeline_module,
        "generate_sql_from_plan_step",
        lambda **_kwargs: GeneratedSQL(sql=candidate, tables_used=["refunds"]),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_sql_tool",
        lambda **_kwargs: SQLToolResult(
            tables_used=["refunds"], safety_status="blocked", blocked_reason="SQL 执行失败。",
            error_type="sql_execution_error", issue_code="mysql_unsupported_date_trunc",
            tool_call=ToolCallTrace(
                tool_name="sql_query", status="error", error_type="sql_execution_error",
                message="SQL 执行失败。",
            ),
        ),
    )
    result = run_text2sql_pipeline(
        question="按月查询退款", user_role="ops", db=object(), trace_id="repair-snapshot",
    )
    assert result.repair_snapshot is not None
    assert result.repair_snapshot.plan_step == snapshot_plan
    assert result.repair_snapshot.candidate_sql == candidate

    observation = _sql_observation(
        request=HarnessRequest(
            question="按月查询退款", run_id="repair-snapshot",
            caller=demo_caller(caller_id="m44", roles=("ops",)), active_sql_role="ops",
        ),
        sql=result.sql, answer_hint=result.answer_hint, tool_result=result.tool_result,
        error_type=result.error_type, message=result.blocked_reason,
        trace_steps=tuple(result.trace_steps), repair_snapshot=result.repair_snapshot,
    )
    assert observation.sql_repair_snapshot == result.repair_snapshot
    public_action = agent_loop_module._safe_observation(observation)
    assert "repair_snapshot" not in json.dumps(public_action, ensure_ascii=False)
    assert candidate not in json.dumps(public_action, ensure_ascii=False)


def test_post_generation_fidelity_failure_keeps_repair_usage_and_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型已真实返回后，即使 fidelity 拦截也必须记账，不能因失败结果漏掉调用。"""

    class Client:
        provider_label = "fixture"
        model = "fixture"
        calls = 0

        def complete(self, **_kwargs: object) -> str:
            self.calls += 1
            return json.dumps({
                "sql": (
                    "SELECT DATE_FORMAT(refunds.processed_at, '%Y-%m-01') AS month, "
                    "1 AS unexpected FROM refunds GROUP BY "
                    "DATE_FORMAT(refunds.processed_at, '%Y-%m-01') ORDER BY month ASC"
                )
            })

    client = Client()
    monkeypatch.setattr(pipeline_module, "get_default_llm_client", lambda: client)
    monkeypatch.setattr(
        pipeline_module,
        "generate_query_plan",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("repair must not replan")),
    )
    result = run_text2sql_pipeline(
        question="按月查询退款", user_role="ops", db=object(), trace_id="repair-usage",
        repair_context=_month_repair_snapshot(), repair_strategy="llm_enriched",
    )
    assert result.error_type == "output_projection_contract_failed"
    repair_trace = next(step for step in result.trace_steps if step.name == "sql_repair")
    assert repair_trace.status == "error"
    assert repair_trace.metadata["repair_strategy"] == "llm_enriched"
    assert repair_trace.metadata["generation_stage"] == "sql_repair"
    assert repair_trace.metadata["llm_call"]["attempt_count"] == 1
    assert client.calls == 1
    observation = ToolObservation(
        tool_name="text2sql", route="sql", execution_status="completed", answer_status="no_answer",
        safety_status="blocked", reason_code="output_projection_contract_failed",
        blocked_reason="生成的查询未通过输出合同校验。", error_type=result.error_type,
        trace_steps=tuple(result.trace_steps),
    )
    consumption = agent_loop_module._consumption(observation, action_id="repair_sql_evidence")
    assert consumption.model_calls == 1
    assert consumption.token_usage_observed is False


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
