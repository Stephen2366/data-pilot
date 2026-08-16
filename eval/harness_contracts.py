"""M35 独立 Harness Eval family：一题一次 Graph 运行，多断言复用同一 ExecutionEvidence。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal

from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.harness.graph import HarnessRuntime, run_harness

HARNESS_CONTRACT_VERSION = "phase4-harness-v1"


@dataclass(frozen=True)
class HarnessScenario:
    """确定性合同题；不是开放问答正确率或真实 provider 评测。"""

    scenario_id: str
    question: str
    expected_route: Literal["sql", "rag", "none"]
    expected_answer_status: str
    caller_trusted: bool = True


SCENARIOS = (
    HarnessScenario("sql", "各渠道订单量是多少？", "sql", "complete"),
    HarnessScenario("rag", "退款政策是什么？", "rag", "complete"),
    HarnessScenario("clarification", "这个怎么处理？", "none", "clarification_required"),
    HarnessScenario("hybrid_unsupported", "查询退款率并说明退款政策", "none", "unsupported"),
    HarnessScenario("caller_untrusted", "各渠道订单量是多少？", "none", "no_answer", caller_trusted=False),
)


@dataclass(frozen=True)
class HarnessExecutionEvidence:
    """同一 Scenario 的唯一 Graph 事实；assertion 不得重新调用 Tool。"""

    scenario_id: str
    invocation_count: int
    route: str
    execution_status: str
    answer_status: str
    safety_status: str
    tool_calls: int
    graph_steps: tuple[str, ...]


@dataclass(frozen=True)
class HarnessAssertion:
    """一条 typed contract assertion 的确定性判定结果。"""

    scenario_id: str
    assertion_id: str
    status: Literal["passed", "failed"]


@dataclass(frozen=True)
class HarnessArtifact:
    """完成 artifact；closed-world validator 防止漏题、重跑或重复 assertion 伪通过。"""

    contract_version: str
    selected_scenario_ids: tuple[str, ...]
    execution_evidence: tuple[HarnessExecutionEvidence, ...]
    assertions: tuple[HarnessAssertion, ...]
    artifact_identity: str


class _FakeSQLTool:
    """Eval local fake：只验证顶层控制合同，不代替 Text2SQL 深链测试。"""

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """返回固定 SQL 成功 Observation，让 Eval 聚焦 Harness 而非 SQL 实现。"""

        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer="sql",
        )


class _FakeRAGTool:
    """Eval local fake：RAGAnswerFlow 自身的 Gate/citation 语义仍由 M33 suite 覆盖。"""

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """返回固定 RAG 成功 Observation，让 Eval 聚焦唯一 route/Tool 合同。"""

        return ToolObservation(
            tool_name="rag_answer_flow", route="rag", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="answer_completed", answer="rag",
        )


def run_harness_contracts(*, scenarios: tuple[HarnessScenario, ...] = SCENARIOS) -> HarnessArtifact:
    """每个 Scenario 只 invoke 一次 Graph，随后从 result 投影多个 assertion。"""

    executions: list[HarnessExecutionEvidence] = []
    assertions: list[HarnessAssertion] = []
    for scenario in scenarios:
        caller = demo_caller(caller_id=f"eval-{scenario.scenario_id}", roles=("ops",)) if scenario.caller_trusted else None
        request = HarnessRequest(
            question=scenario.question,
            run_id=f"harness-eval-{scenario.scenario_id}",
            caller=caller,
            active_sql_role="ops" if caller else None,
            force_new_pipeline=False,
        )
        result = run_harness(request=request, runtime=HarnessRuntime(sql_tool=_FakeSQLTool(), rag_tool=_FakeRAGTool()))
        evidence = HarnessExecutionEvidence(
            scenario_id=scenario.scenario_id,
            invocation_count=1,
            route=result.route,
            execution_status=result.execution_status,
            answer_status=result.answer_status,
            safety_status=result.safety_status,
            tool_calls=len(result.observation.tool_calls) if result.observation else 0,
            graph_steps=result.graph_steps,
        )
        executions.append(evidence)
        assertions.extend(
            (
                HarnessAssertion(scenario.scenario_id, "route", "passed" if result.route == scenario.expected_route else "failed"),
                HarnessAssertion(
                    scenario.scenario_id, "answer_status",
                    "passed" if result.answer_status == scenario.expected_answer_status else "failed",
                ),
                HarnessAssertion(
                    scenario.scenario_id, "single_tool",
                    "passed" if (result.observation is None or len(result.observation.tool_calls) <= 1) else "failed",
                ),
            )
        )
    unsigned = {
        "contract_version": HARNESS_CONTRACT_VERSION,
        "selected_scenario_ids": [item.scenario_id for item in scenarios],
        "execution_evidence": [asdict(item) for item in executions],
        "assertions": [asdict(item) for item in assertions],
    }
    artifact = HarnessArtifact(
        contract_version=HARNESS_CONTRACT_VERSION,
        selected_scenario_ids=tuple(item.scenario_id for item in scenarios),
        execution_evidence=tuple(executions),
        assertions=tuple(assertions),
        artifact_identity=sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
    )
    validate_completed_artifact(artifact, scenarios=scenarios)
    return artifact


def validate_completed_artifact(artifact: HarnessArtifact, *, scenarios: tuple[HarnessScenario, ...] = SCENARIOS) -> None:
    """closed-world 校验：题集、一次 execution、三条 assertion 都必须恰好闭合。"""

    expected_ids = tuple(item.scenario_id for item in scenarios)
    if artifact.contract_version != HARNESS_CONTRACT_VERSION or artifact.selected_scenario_ids != expected_ids:
        raise ValueError("Harness artifact contract/scenario 不匹配")
    execution_ids = tuple(item.scenario_id for item in artifact.execution_evidence)
    if execution_ids != expected_ids or any(item.invocation_count != 1 for item in artifact.execution_evidence):
        raise ValueError("每题必须恰好一份、且只 invoke 一次 Graph 的 ExecutionEvidence")
    expected_assertion_ids = [(scenario_id, kind) for scenario_id in expected_ids for kind in ("route", "answer_status", "single_tool")]
    actual_assertion_ids = [(item.scenario_id, item.assertion_id) for item in artifact.assertions]
    if actual_assertion_ids != expected_assertion_ids or any(item.status != "passed" for item in artifact.assertions):
        raise ValueError("Harness assertion 缺失、重复或未通过")
