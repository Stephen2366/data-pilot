"""M27A 地基测试：只穿过 ``Evaluator.evaluate()`` 这个 Interface，不调用真实 LLM。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from eval.catalog import CatalogError, load_catalog
from eval.assertions import score_assertion
from eval.contracts import AssertionContract, EvalRunSpec, ExecutionEvidence, ExecutionProtocol, MetricMappingSpec, ResolvedRuntimeIdentity
from eval.evaluator import Evaluator
from eval.environment import SQLiteRunEnvironmentFactory, _resolved_runtime_values
from eval.ports import FileCheckpointStore, MemoryCheckpointStore
from eval.projectors import SuitePolicy, exit_code_for_gate, project_eval_run
from eval.reporting import build_langfuse_assertion_payloads, render_markdown
from eval.selectors import load_selector
from engine.nl2sql.prompt import build_query_plan_prompt
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.retriever import retrieve_schema


def _catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.yaml"
    path.write_text(
        """
contract_version: m27-v2
scenarios:
  - id: june_gmv
    question: 2026 年 6 月 GMV 是多少？
    user_role: ops
    classification: core
    tags: [gmv]
    assertions:
      - id: result
        kind: result_match
        spec:
          reference_sql: SELECT 1 AS gmv
          columns: [gmv]
      - id: output
        kind: output_contract
        spec:
          columns: [gmv]
      - id: trace
        kind: trace_complete
        spec:
          required_steps:
            - {type: schema_context, status: success}
            - {type: sql_execution, status: success}
""".strip(),
        encoding="utf-8",
    )
    return path


class _FakePipeline:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, **_: object):
        self.calls += 1
        return 200, {"safety_status": "passed", "columns": ["gmv"], "rows": [{"gmv": 1}]}, (
            {"step_type": "schema_context", "status": "success", "metadata": {"tables": ["orders"]}},
            {"step_type": "sql_execution", "status": "success", "metadata": {}},
        )


class _FakeOracle:
    def execute(self, _: str):
        return ({"gmv": 1},)


class _Environment:
    def __init__(self, pipeline: _FakePipeline) -> None:
        self.pipeline = pipeline
        self.oracle = _FakeOracle()
        self.resolved_runtime_identity = ResolvedRuntimeIdentity({"pipeline_mode": "new_text2sql"})
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Factory:
    def __init__(self, environment: _Environment) -> None:
        self.environment = environment
        self.calls = 0

    def create(self, _: EvalRunSpec) -> _Environment:
        self.calls += 1
        return self.environment


def test_evaluator_runs_multiple_assertions_from_one_pipeline_call(tmp_path: Path) -> None:
    """同一 scenario 的 Result/Output/Trace 必须共享一张答卷。"""

    catalog = load_catalog(_catalog_file(tmp_path))
    pipeline = _FakePipeline()
    environment = _Environment(pipeline)
    checkpoints = MemoryCheckpointStore()
    run = Evaluator(catalog=catalog, environment_factory=_Factory(environment), checkpoint_store=checkpoints).evaluate(
        EvalRunSpec(run_id="m27-test", scenario_ids=("june_gmv",), execution_protocol=ExecutionProtocol())
    )

    assert run.run_status == "completed"
    assert pipeline.calls == 1
    assert len(run.scenario_runs[0].assertion_results) == 3
    assert {item.status for item in run.scenario_runs[0].assertion_results} == {"passed"}
    assert len(checkpoints.checkpoints) == 1
    assert environment.closed is True


def test_query_plan_timeout_is_external_unavailable_and_not_observed(tmp_path: Path) -> None:
    """没有候选 SQL 的 provider timeout 不能被空输出投影成业务失败。"""

    class TimeoutPipeline(_FakePipeline):
        def execute(self, **_: object):
            self.calls += 1
            return 200, {"safety_status": "blocked", "error_type": "llm_generation_error", "columns": [], "rows": []}, (
                {"step_type": "query_plan", "status": "error", "error_type": "llm_generation_error", "metadata": {"error_subtype": "timeout"}},
            )

    catalog = load_catalog(_catalog_file(tmp_path))
    run = Evaluator(
        catalog=catalog,
        environment_factory=_Factory(_Environment(TimeoutPipeline())),
        checkpoint_store=MemoryCheckpointStore(),
    ).evaluate(EvalRunSpec(run_id="m27-timeout", scenario_ids=("june_gmv",)))

    scenario_run = run.scenario_runs[0]
    assert scenario_run.evidence.execution_status == "external_unavailable"
    assert {(item.status, item.reason) for item in scenario_run.assertion_results} == {("not_observed", "external_unavailable")}

    projected = project_eval_run(run, SuitePolicy("core", ("june_gmv",), {"core": "required"}, {}, {"june_gmv": "core"}))
    assert projected.gate.outcome == "inconclusive"
    assert projected.gate.required_not_observed == 3


def test_committed_vertical_slice_catalog_loads() -> None:
    """已迁移 scenario 直接存放在 canonical catalog，而不是藏在测试 fixture。"""

    catalog = load_catalog(Path("eval/cases/catalog/scenarios.yaml"))

    assert [scenario.scenario_id for scenario in catalog.scenarios] == [
        "june_gmv", "unsafe_drop_orders", "unsafe_delete_refund", "pii_email_phone_block",
        "admin_contact_block", "missing_product_supplier_rejection",
        "knowledge_doc_order_attribution_rejection", "unsupported_multi_step_rejection",
        "active_products_top10", "june_fixed_coupon_basic_info", "june_net_revenue",
        "top_device_conversion", "june_fixed_coupon_top_channel", "june_completed_orders_top10",
        "channel_order_ranking",
        "june_product_sales_top5", "june_channel_gmv_ranking", "june_root_category_sales",
        "signed_net_refund_amount", "channel_net_refund_amount", "order_item_amount_reconciliation",
        "june_product_refund_rate_ranking", "digital_electronics_recursive_item_gmv", "june_avg_price_history",
        "june_actual_amount_sum", "june_channel_gmv_dashboard", "june_channel_refund_rate_ranking",
        "june_coupon_type_gmv",
    ]
    assert [item.kind for item in catalog.scenarios[0].assertions] == [
        "result_match", "output_contract", "schema_context", "query_plan", "trace_complete"
    ]


def test_catalog_rejects_unknown_assertion_before_execution(tmp_path: Path) -> None:
    path = _catalog_file(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("kind: output_contract", "kind: imaginary"), encoding="utf-8")

    with pytest.raises(CatalogError, match="unknown kind"):
        load_catalog(path)


def test_catalog_hash_ignores_yaml_mapping_order(tmp_path: Path) -> None:
    first = _catalog_file(tmp_path)
    second = tmp_path / "second.yaml"
    payload = yaml.safe_load(first.read_text(encoding="utf-8"))
    scenario = payload["scenarios"][0]
    payload["scenarios"][0] = {key: scenario[key] for key in reversed(list(scenario))}
    second.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    assert load_catalog(first).catalog_hash == load_catalog(second).catalog_hash


def test_file_checkpoint_store_refuses_run_id_reuse_and_writes_completed_artifact(tmp_path: Path) -> None:
    catalog = load_catalog(_catalog_file(tmp_path))
    pipeline = _FakePipeline()
    store = FileCheckpointStore(checkpoint_root=tmp_path / "temporary", artifact_root=tmp_path / "artifacts")
    evaluator = Evaluator(catalog=catalog, environment_factory=_Factory(_Environment(pipeline)), checkpoint_store=store)

    run = evaluator.evaluate(EvalRunSpec(run_id="m27-safe-run", scenario_ids=("june_gmv",)))

    assert run.run_status == "completed"
    assert (tmp_path / "artifacts" / "m27-safe-run.json").is_file()
    assert (tmp_path / "temporary" / "m27-safe-run" / "checkpoints" / "june_gmv--r1.json").is_file()
    with pytest.raises(FileExistsError, match="resume is not implemented"):
        evaluator.evaluate(EvalRunSpec(run_id="m27-safe-run", scenario_ids=("june_gmv",)))


def test_completed_artifact_does_not_persist_result_rows_or_pii(tmp_path: Path) -> None:
    class SensitivePipeline(_FakePipeline):
        def execute(self, **_: object):
            self.calls += 1
            return 200, {
                "safety_status": "passed", "columns": ["gmv"], "rows": [{"gmv": 1, "email": "alice@example.com"}],
                "answer": "alice@example.com",
            }, ()

    catalog = load_catalog(_catalog_file(tmp_path))
    store = FileCheckpointStore(checkpoint_root=tmp_path / "temporary", artifact_root=tmp_path / "artifacts")
    Evaluator(
        catalog=catalog,
        environment_factory=_Factory(_Environment(SensitivePipeline())),
        checkpoint_store=store,
    ).evaluate(EvalRunSpec(run_id="m27-redaction", scenario_ids=("june_gmv",)))

    artifact = (tmp_path / "artifacts" / "m27-redaction.json").read_text(encoding="utf-8")
    assert "alice@example.com" not in artifact
    assert '"rows"' not in artifact
    assert '"candidate_row_count": 1' in artifact
    assert '"candidate_rows_sha256"' in artifact


def test_sqlite_environment_scores_expected_rejection_without_llm(tmp_path: Path) -> None:
    """真实 FastAPI/SQLite adapter 的拒绝路径在语义校验前结束，不发起模型调用。"""

    path = tmp_path / "rejection.yaml"
    path.write_text(
        """
contract_version: m27-v2
scenarios:
  - id: missing_supplier
    question: 查询商品的供应商名称
    user_role: ops
    classification: core
    tags: [expected_rejection]
    assertions:
      - id: rejection
        kind: expected_rejection
        spec:
          issue_tags: [missing_column]
          blocked_via: semantic_request_validation
""".strip(),
        encoding="utf-8",
    )
    run = Evaluator(
        catalog=load_catalog(path),
        environment_factory=SQLiteRunEnvironmentFactory(trace_root=tmp_path / "traces"),
        checkpoint_store=MemoryCheckpointStore(),
    ).evaluate(EvalRunSpec(run_id="m27-rejection", scenario_ids=("missing_supplier",)))

    assert run.run_status == "completed"
    assert run.scenario_runs[0].evidence.execution_status == "rejected"
    assert run.scenario_runs[0].assertion_results[0].status == "passed"


def test_plan_join_and_metric_assertions_use_same_structured_trace_evidence() -> None:
    """Plan/Join/Metric 不再落入旧 runner 的默认 ok，且不会重新调用 pipeline。"""

    catalog = load_catalog(Path("eval/cases/catalog/scenarios.yaml"))
    scenario = next(item for item in catalog.scenarios if item.scenario_id == "june_channel_gmv_ranking")
    evidence = ExecutionEvidence(
        run_id="test", scenario_id=scenario.scenario_id, replicate_id=1, execution_status="completed", status_code=200,
        response={"safety_status": "passed"}, trace_steps=({
            "step_type": "query_plan", "status": "success", "metadata": {"plan_steps": [{
                "step_type": "sql_query", "tables": ["channels", "orders"], "joins": ["orders_channel"],
                "metrics": ["gmv"], "group_by": ["channel_name"], "order_by": ["gmv DESC"],
                "output_columns": ["channel_name", "gmv"], "columns": ["orders.order_amount"],
            }]},
        },),
    )
    query_plan = next(item for item in scenario.assertions if item.kind == "query_plan")
    join_path = next(item for item in scenario.assertions if item.kind == "join_path")
    metric = AssertionContract("metric", "metric_mapping", MetricMappingSpec(("orders",), ("orders.order_amount",), ("gmv",)))

    assert score_assertion(query_plan, evidence).status == "passed"
    assert score_assertion(join_path, evidence).status == "passed"
    assert score_assertion(metric, evidence).status == "passed"
    missing_join = ExecutionEvidence(**{**evidence.__dict__, "trace_steps": ({"step_type": "query_plan", "status": "success", "metadata": {"plan_steps": [{"step_type": "sql_query", "tables": ["orders"], "joins": [], "metrics": [], "columns": []}]}},)})
    assert score_assertion(join_path, missing_join).status == "failed"
    assert score_assertion(metric, missing_join).status == "failed"


def test_actual_amount_metric_contract_accepts_qualified_plan_column() -> None:
    """合同的 actual_amount 与计划的 orders.actual_amount 是同一业务字段。"""

    catalog = load_catalog(Path("eval/cases/catalog/scenarios.yaml"))
    scenario = next(item for item in catalog.scenarios if item.scenario_id == "june_actual_amount_sum")
    metric = scenario.assertions[0]
    evidence = ExecutionEvidence(
        run_id="test", scenario_id=scenario.scenario_id, replicate_id=1, execution_status="completed", status_code=200,
        response={"safety_status": "passed"}, trace_steps=({
            "step_type": "query_plan", "status": "success", "metadata": {"plan_steps": [{
                "step_type": "sql_query", "tables": ["orders"], "columns": ["orders.actual_amount"], "metrics": ["net_revenue"],
            }]},
        },),
    )

    assert score_assertion(metric, evidence).status == "passed"


def test_channel_gmv_retrieval_keeps_metric_and_snapshot_guidance() -> None:
    """渠道 GMV 不应被 orders_wide 的字段别名挤掉 gmv metric。"""

    domain_schema = load_domain_schema()
    question = "查看 2026 年 6 月各渠道 GMV；可使用订单明细口径或 orders_wide 月度快照口径。"
    result = retrieve_schema(question=question, user_role="ops", top_k=30, domain_schema=domain_schema)
    graph = build_schema_graph(result.merged_hits, domain_schema=domain_schema)
    prompt = build_query_plan_prompt(question=question, schema_graph=graph, metrics=domain_schema.metrics)

    assert "gmv" in graph.metrics
    assert "snapshot_at" in prompt


def test_runtime_identity_records_milvus_embedding_and_schema_corpus() -> None:
    """同为 Milvus 的运行也必须能从 artifact 区分 embedding 与 collection。"""

    settings = SimpleNamespace(
        llm_provider="qwen", qwen_model="qwen3.7-plus", llm_model="unused",
        schema_vector_backend="milvus", schema_embedding_provider="dashscope",
        qwen_embedding_model="qwen3.7-text-embedding", qwen_embedding_dimensions=1024,
        siliconflow_embedding_model="BAAI/bge-m3", siliconflow_embedding_dimensions=None,
        milvus_collection="fixture_m27_qwen", llm_timeout_seconds=45.0,
        llm_max_retries=0, llm_retry_backoff_seconds=1.0,
    )

    values = _resolved_runtime_values(settings, EvalRunSpec(run_id="runtime-fixture", scenario_ids=("june_gmv",)))

    assert values["schema_embedding_model"] == "qwen3.7-text-embedding"
    assert values["schema_embedding_dimensions"] == 1024
    assert values["milvus_collection"] == "fixture_m27_qwen"
    assert values["schema_docs_count"] == 195
    assert values["schema_docs_hash"] == "8a8b6626a4cbec6197d9625ec12d5d40668025476f823eaa9458647cecd8d41a"


def test_selector_projector_uses_logical_denominators_and_markdown_only_reads_projected_facts(tmp_path: Path) -> None:
    """Reliability replicate 不扩大分母，gate 与 Markdown 均从同一 EvalRun 明细推导。"""

    catalog = load_catalog(_catalog_file(tmp_path))
    pipeline = _FakePipeline()
    run = Evaluator(
        catalog=catalog,
        environment_factory=_Factory(_Environment(pipeline)),
        checkpoint_store=MemoryCheckpointStore(),
    ).evaluate(EvalRunSpec(
        run_id="m27-project", scenario_ids=("june_gmv",), execution_protocol=ExecutionProtocol(replicate_count=3),
        suite_policy={"effects_by_classification": {"core": "required"}},
    ))
    policy = SuitePolicy(
        suite_id="reliability", selected_scenario_ids=("june_gmv",),
        effects_by_classification={"core": "required"}, assertion_overrides={},
        scenario_classifications={"june_gmv": "core"},
    )
    projected = project_eval_run(run, policy)

    assert pipeline.calls == 3
    assert projected.assertion_views["result_match"].eligible == 1
    assert projected.assertion_views["result_match"].observed == 1
    assert projected.execution["logical_scenarios"] == 1
    assert projected.execution["physical_attempts"] == 3
    assert projected.gate.outcome == "passed"
    assert exit_code_for_gate(projected.gate) == 0
    markdown = render_markdown(run, projected)
    assert "## Assertion views" in markdown
    payloads = build_langfuse_assertion_payloads(run, projected)
    assert len(payloads) == 9
    assert all("rows" not in item and "sql" not in item for item in payloads)


def test_selector_loader_reuses_canonical_scenarios_without_copying_yaml() -> None:
    catalog = load_catalog(Path("eval/cases/catalog/scenarios.yaml"))
    selector = load_selector(Path("eval/cases/catalog/selectors/reliability.yaml"), catalog)

    assert selector.execution_protocol.replicate_count == 3
    assert selector.scenario_ids == ("june_gmv", "active_products_top10")


def test_interrupted_and_abandoned_runs_never_enter_projector(tmp_path: Path) -> None:
    """可捕获中断保留 partial manifest；硬崩溃遗留 running 被读取为 abandoned。"""

    class InterruptingPipeline(_FakePipeline):
        def execute(self, **_: object):
            raise KeyboardInterrupt("test interrupt")

    catalog = load_catalog(_catalog_file(tmp_path))
    store = FileCheckpointStore(checkpoint_root=tmp_path / "temporary", artifact_root=tmp_path / "artifacts")
    run = Evaluator(
        catalog=catalog,
        environment_factory=_Factory(_Environment(InterruptingPipeline())),
        checkpoint_store=store,
    ).evaluate(EvalRunSpec(run_id="m27-interrupt", scenario_ids=("june_gmv",)))
    policy = SuitePolicy("core", ("june_gmv",), {"core": "required"}, {}, {"june_gmv": "core"})

    assert run.run_status == "interrupted"
    with pytest.raises(ValueError, match="only completed"):
        project_eval_run(run, policy)

    running = Evaluator(
        catalog=catalog,
        environment_factory=_Factory(_Environment(_FakePipeline())),
        checkpoint_store=MemoryCheckpointStore(),
    )._new_run(EvalRunSpec(run_id="m27-abandoned", scenario_ids=("june_gmv",)), run_status="running", scenario_runs=())
    FileCheckpointStore(checkpoint_root=tmp_path / "temporary", artifact_root=tmp_path / "artifacts").start(running)
    assert store.inspect_lifecycle("m27-abandoned") == "abandoned"
