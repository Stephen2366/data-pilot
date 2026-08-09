"""M27 的深 module：一次入口完成 catalog 选择、环境生命周期、执行、oracle、评分与 checkpoint。

调用方只需要 ``Evaluator(...).evaluate(run_spec)``。复杂的调用次数不变量、同 snapshot oracle、
not_observed 语义和 partial-run 落盘都集中在这里，形成一个高 leverage 的 Interface。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from eval.assertions import score_assertion
from eval.catalog import CatalogError, run_spec_hash, selected_contract_hash, select_scenarios, suite_policy_hash
from eval.contracts import (
    ARTIFACT_SCHEMA_VERSION,
    CONTRACT_VERSION,
    Catalog,
    EvalRun,
    EvalRunSpec,
    ExecutionEvidence,
    ScenarioContract,
    ScenarioRun,
)
from eval.ports import CheckpointStore, RunEnvironmentFactory


class Evaluator:
    """M27 的唯一执行 Interface；内部依赖在构造时注入，便于 fake adapter 验证。"""

    def __init__(self, *, catalog: Catalog, environment_factory: RunEnvironmentFactory, checkpoint_store: CheckpointStore) -> None:
        self._catalog = catalog
        self._environment_factory = environment_factory
        self._checkpoint_store = checkpoint_store

    def evaluate(self, run_spec: EvalRunSpec) -> EvalRun:
        """执行一轮 EvalRun，并保证每个 scenario/replicate 最多一次 PipelinePort 调用。"""

        scenarios = select_scenarios(self._catalog, run_spec.scenario_ids)
        populated_spec = self._populate_hashes(run_spec, scenarios)
        running = self._new_run(populated_spec, run_status="running", scenario_runs=())
        self._checkpoint_store.start(running)
        environment = None
        scenario_runs: list[ScenarioRun] = []
        try:
            environment = self._environment_factory.create(populated_spec)
            for scenario in scenarios:
                for replicate_id in range(1, populated_spec.execution_protocol.replicate_count + 1):
                    scenario_run = self._execute_once(environment, populated_spec, scenario, replicate_id)
                    scenario_runs.append(scenario_run)
                    self._checkpoint_store.checkpoint(scenario_run)
            completed = self._new_run(
                populated_spec,
                run_status="completed",
                scenario_runs=tuple(scenario_runs),
                resolved_runtime_identity=environment.resolved_runtime_identity,
            )
            self._checkpoint_store.finalize(completed)
            return completed
        except KeyboardInterrupt as exc:
            interrupted = self._new_run(
                populated_spec,
                run_status="interrupted",
                scenario_runs=tuple(scenario_runs),
                resolved_runtime_identity=getattr(environment, "resolved_runtime_identity", None),
                failure_reason=f"evaluation_interrupted: {exc}",
            )
            self._checkpoint_store.fail(interrupted)
            return interrupted
        except Exception as exc:  # noqa: BLE001 - artifact 必须保留可读的失败原因。
            failed = self._new_run(
                populated_spec,
                run_status="failed",
                scenario_runs=tuple(scenario_runs),
                resolved_runtime_identity=getattr(environment, "resolved_runtime_identity", None),
                failure_reason=f"environment_or_evaluation_failed: {exc}",
            )
            self._checkpoint_store.fail(failed)
            return failed
        finally:
            if environment is not None:
                environment.close()

    def _execute_once(self, environment: Any, run_spec: EvalRunSpec, scenario: ScenarioContract, replicate_id: int) -> ScenarioRun:
        """执行唯一候选调用，再在同一 environment 的 oracle 证据上评分全部 assertions。"""
        status_code, response, trace_steps = environment.pipeline.execute(
            question=scenario.question,
            user_role=scenario.user_role,
            pipeline_mode=run_spec.execution_protocol.pipeline_mode,
            fusion_strategy=run_spec.execution_protocol.schema_fusion_strategy,
        )
        execution_status = _execution_status(status_code, response, trace_steps)
        expected_rows, oracle_error = self._oracle_rows(environment.oracle, scenario)
        evidence = ExecutionEvidence(
            run_id=run_spec.run_id,
            scenario_id=scenario.scenario_id,
            replicate_id=replicate_id,
            execution_status=execution_status,
            status_code=status_code,
            response=response,
            trace_steps=trace_steps,
            expected_rows=expected_rows,
            oracle_error=oracle_error,
        )
        results = tuple(score_assertion(assertion, evidence) for assertion in scenario.assertions)
        return ScenarioRun(scenario.scenario_id, replicate_id, evidence, results)

    def _oracle_rows(self, oracle: Any, scenario: ScenarioContract) -> tuple[tuple[dict[str, Any], ...] | None, str | None]:
        """同一 scenario 的多条 result assertion 共用一次 oracle 结果，避免 scorer 私下访问 DB。"""

        result_assertions = [item for item in scenario.assertions if item.kind == "result_match"]
        if not result_assertions:
            return None, None
        sql_values = {item.spec.reference_sql for item in result_assertions if item.spec is not None}
        if len(sql_values) != 1:
            return None, "scenario_has_conflicting_result_oracles"
        try:
            return tuple(oracle.execute(next(iter(sql_values)))), None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    def _populate_hashes(self, spec: EvalRunSpec, scenarios: tuple[ScenarioContract, ...]) -> EvalRunSpec:
        """计算并核对四层 run identity，拒绝调用方伪造或陈旧 hash。"""
        selected_hash = selected_contract_hash(scenarios)
        policy_hash = suite_policy_hash(
            scenario_ids=spec.scenario_ids,
            classifications={item.scenario_id: item.classification for item in scenarios},
            gate_policy=spec.suite_policy,
        )
        calculated_spec_hash = run_spec_hash(
            selected_hash=selected_hash,
            policy_hash=policy_hash,
            protocol={"pipeline_mode": spec.execution_protocol.pipeline_mode, "schema_fusion_strategy": spec.execution_protocol.schema_fusion_strategy, "replicate_count": spec.execution_protocol.replicate_count},
            oracle_fixture_identity=spec.oracle_fixture_identity,
            constraints=spec.requested_runtime_constraints,
        )
        for label, supplied, calculated in (("selected_contract_hash", spec.selected_contract_hash, selected_hash), ("suite_policy_hash", spec.suite_policy_hash, policy_hash), ("run_spec_hash", spec.run_spec_hash, calculated_spec_hash)):
            if supplied and supplied != calculated:
                raise CatalogError(f"{label} mismatch: supplied={supplied} calculated={calculated}")
        return replace(spec, selected_contract_hash=selected_hash, suite_policy_hash=policy_hash, run_spec_hash=calculated_spec_hash)

    def _new_run(self, spec: EvalRunSpec, *, run_status: str, scenario_runs: tuple[ScenarioRun, ...], resolved_runtime_identity: Any = None, failure_reason: str | None = None) -> EvalRun:
        """集中构造生命周期 manifest，避免 completed/failed 的版本字段漂移。"""
        return EvalRun(
            run_id=spec.run_id,
            run_status=run_status,  # type: ignore[arg-type]
            contract_version=CONTRACT_VERSION,
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            catalog_hash=self._catalog.catalog_hash,
            selected_contract_hash=spec.selected_contract_hash,
            suite_policy_hash=spec.suite_policy_hash,
            suite_policy=spec.suite_policy,
            run_spec_hash=spec.run_spec_hash,
            requested_runtime_constraints=spec.requested_runtime_constraints,
            resolved_runtime_identity=resolved_runtime_identity,
            scenario_runs=scenario_runs,
            failure_reason=failure_reason,
        )


def _execution_status(status_code: int, response: dict[str, Any], trace_steps: tuple[dict[str, Any], ...]) -> str:
    """把 HTTP/业务响应翻译为中性事实，不在这里判断拒绝是否符合期望。

    API 顶层响应为安全起见通常只保留 ``error_type``；更细的 provider 错误种类位于对应
    trace step 的 ``metadata.error_subtype``。两处都检查，才能把 QueryPlan timeout 这类
    “没有候选答卷”的情况记成 external_unavailable，而不是误写成业务拒绝。
    """

    transient_subtypes = {"timeout", "network_error", "http_429", "http_5xx"}
    trace_subtypes = {
        str((step.get("metadata") or {}).get("error_subtype"))
        for step in trace_steps
        if isinstance(step, dict) and isinstance(step.get("metadata"), dict)
    }
    if status_code >= 500 or response.get("error_subtype") in transient_subtypes or trace_subtypes & transient_subtypes:
        return "external_unavailable"
    if status_code != 200:
        return "pipeline_error"
    if response.get("safety_status") == "blocked":
        return "rejected"
    if response.get("error_type"):
        return "pipeline_error"
    return "completed"
