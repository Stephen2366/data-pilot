"""M27 评测投影：从完成的 ``EvalRun`` 明细推导分母、gate 与 diagnostic 视图。

这里故意不认识 FastAPI、LLM 或 Markdown。它像数据库的只读 materialized view：同一份
ScenarioRun 明细可以被 CLI、Markdown 和 LangFuse adapter 消费，却不会生成第二套评分事实。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from eval.contracts import ARTIFACT_SCHEMA_VERSION, PROJECTOR_VERSION, AssertionResult, EvalRun


GateEffect = Literal["required", "advisory", "excluded"]
GateOutcome = Literal["passed", "failed", "inconclusive"]


@dataclass(frozen=True)
class SuitePolicy:
    """一次视图的选择与 gate 规则；不反写入 ``AssertionResult``。"""

    suite_id: str
    selected_scenario_ids: tuple[str, ...]
    effects_by_classification: dict[str, GateEffect]
    assertion_overrides: dict[str, GateEffect]
    scenario_classifications: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AssertionCounts:
    """单个 assertion kind 的正交分母；``unavailable`` 只是 not_observed 的切片。"""

    eligible: int
    observed: int
    passed: int
    failed: int
    not_observed: int
    unavailable: int
    manual_evidence_required: int


@dataclass(frozen=True)
class GateResult:
    suite_id: str
    outcome: GateOutcome
    required_passed: int
    required_failed: int
    required_not_observed: int


@dataclass(frozen=True)
class ProjectedEval:
    """报告和 adapter 唯一可消费的派生事实。"""

    projector_version: str
    run_id: str
    assertion_views: dict[str, AssertionCounts]
    execution: dict[str, int]
    gate: GateResult


def project_eval_run(run: EvalRun, policy: SuitePolicy) -> ProjectedEval:
    """从 completed artifact 机械推导逻辑 scenario/assertion 的统计和 gate。

    replicate 会合并成同一 ``(scenario_id, assertion_id)`` 逻辑事实，因此 Reliability 的重试
    不会偷偷扩大自然语言问题分母。任一 replicate failed 优先；全 passed 才通过；其余保留
    ``not_observed``，避免把 unavailable 伪装成 semantic wrong。
    """

    if run.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
        raise ValueError(f"unsupported artifact schema: {run.artifact_schema_version}")
    if run.run_status != "completed":
        raise ValueError(f"only completed EvalRun may enter projector: {run.run_status}")
    selected = set(policy.selected_scenario_ids)
    runs = [item for item in run.scenario_runs if item.scenario_id in selected]
    if {item.scenario_id for item in runs} - selected:
        raise AssertionError("unreachable selected filter")

    # 同一 assertion 的多个 replicate 先归约为单个逻辑 outcome。
    grouped: dict[tuple[str, str], list[AssertionResult]] = {}
    for scenario_run in runs:
        for result in scenario_run.assertion_results:
            grouped.setdefault((scenario_run.scenario_id, result.assertion_id), []).append(result)

    classifications = _scenario_classifications(run, policy)
    logical = {key: _reduce_replicates(values) for key, values in grouped.items()}
    views: dict[str, list[AssertionResult]] = {}
    required: list[AssertionResult] = []
    for (scenario_id, assertion_id), result in logical.items():
        views.setdefault(result.kind, []).append(result)
        effect = policy.assertion_overrides.get(
            f"{scenario_id}.{assertion_id}", policy.effects_by_classification.get(classifications.get(scenario_id, ""), "excluded")
        )
        if effect == "required":
            required.append(result)

    assertion_views = {kind: _counts(results) for kind, results in sorted(views.items())}
    gate = _gate(policy.suite_id, required)
    execution = _execution_counts(runs)
    return ProjectedEval(PROJECTOR_VERSION, run.run_id, assertion_views, execution, gate)


def exit_code_for_gate(gate: GateResult, *, fail_closed_inconclusive: bool = False) -> int:
    """CLI policy adapter；Evaluator / EvalRun 不感知 CI 是否对 inconclusive fail-closed。"""

    if gate.outcome == "passed":
        return 0
    if gate.outcome == "inconclusive" and not fail_closed_inconclusive:
        return 0
    return 2


def _scenario_classifications(run: EvalRun, policy: SuitePolicy) -> dict[str, str]:
    """classification 是 catalog identity 的一部分；当前 artifact 只存 result，故由 policy 注入。

    CLI 构造 policy 时已经基于已加载 catalog 选择场景。这里的默认 excluded 保证未知场景
    不会意外成为 required，而不是猜测它属于 Core。
    """

    return policy.scenario_classifications


def _reduce_replicates(results: list[AssertionResult]) -> AssertionResult:
    """将 retry/reliability 结果归约为一条逻辑 assertion，fail 优先。"""
    if any(item.status == "failed" for item in results):
        return next(item for item in results if item.status == "failed")
    if results and all(item.status == "passed" for item in results):
        return results[0]
    return next(item for item in results if item.status == "not_observed")


def _counts(results: list[AssertionResult]) -> AssertionCounts:
    """按固定数学关系统计 eligible/observed/not_observed 及原因切片。"""
    passed = sum(item.status == "passed" for item in results)
    failed = sum(item.status == "failed" for item in results)
    not_observed = sum(item.status == "not_observed" for item in results)
    unavailable = sum(item.status == "not_observed" and item.reason == "external_unavailable" for item in results)
    manual = sum(item.status == "not_observed" and item.reason == "manual_evidence_required" for item in results)
    return AssertionCounts(
        eligible=len(results), observed=passed + failed, passed=passed, failed=failed,
        not_observed=not_observed, unavailable=unavailable, manual_evidence_required=manual,
    )


def _gate(suite_id: str, results: list[AssertionResult]) -> GateResult:
    """从 required assertion 观察事实推导三态 suite gate。"""
    passed = sum(item.status == "passed" for item in results)
    failed = sum(item.status == "failed" for item in results)
    missing = sum(item.status == "not_observed" for item in results)
    outcome: GateOutcome = "failed" if failed else "inconclusive" if missing or not results else "passed"
    return GateResult(suite_id, outcome, passed, failed, missing)


def _execution_counts(runs: list[object]) -> dict[str, int]:
    """execution 与语义 assertion 分开统计；同一 scenario 的 replicate 不算独立题。"""

    by_scenario: dict[str, list[tuple[str, int]]] = {}
    for scenario_run in runs:
        evidence = getattr(scenario_run, "evidence")
        by_scenario.setdefault(evidence.scenario_id, []).append((evidence.execution_status, evidence.physical_attempts))
    statuses = [values for values in by_scenario.values()]
    return {
        "logical_scenarios": len(statuses),
        "logical_completed": sum(any(status in {"completed", "rejected"} for status, _ in values) for values in statuses),
        "logical_external_unavailable": sum(all(status == "external_unavailable" for status, _ in values) for values in statuses),
        "logical_pipeline_error": sum(all(status == "pipeline_error" for status, _ in values) for values in statuses),
        "physical_attempts": sum(attempts for values in statuses for _, attempts in values),
    }
