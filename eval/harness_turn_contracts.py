"""M36 sequence Eval：用多 turn 事实验证 clarification checkpoint 的恢复合同。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from threading import Barrier, Lock
from typing import Literal

from app.schemas.agent import ToolCallTrace
from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.harness.graph import HarnessRuntime
from engine.harness.thread import ThreadCheckpointManager
from engine.harness.turn import AgentTurnResult, TurnRequest, clear_thread, run_turn

HARNESS_TURN_CONTRACT_VERSION = "phase4-harness-turn-v1"
ASSERTION_IDS = ("sequence_closed", "graph_budget", "terminal", "version_chain", "single_resume")


@dataclass(frozen=True)
class TurnScenario:
    """确定性 sequence 题；每题聚焦一种 lifecycle/context 边界。"""

    scenario_id: str
    kind: Literal["subject", "analytics", "wrong_owner", "version", "expiry", "clear", "concurrent", "budget"]
    expected_reason: str


SCENARIOS = (
    TurnScenario("subject_to_rag", "subject", "answer_completed"),
    TurnScenario("analytics_to_sql", "analytics", "sql_completed"),
    TurnScenario("wrong_owner_then_owner", "wrong_owner", "answer_completed"),
    TurnScenario("stale_version_then_owner", "version", "answer_completed"),
    TurnScenario("expired_pending", "expiry", "thread_expired"),
    TurnScenario("cleared_pending", "clear", "thread_cleared"),
    TurnScenario("concurrent_single_claim", "concurrent", "answer_completed"),
    TurnScenario("resume_budget_stop", "budget", "budget_exhausted"),
)


@dataclass(frozen=True)
class TurnExecutionEvidence:
    """一个 sequence 内某次 HTTP 等价 attempt 的安全事实。"""

    sequence_id: str
    turn_id: str
    turn_index: int
    turn_action: str
    graph_invocation_count: int
    route: str
    execution_status: str
    answer_status: str
    reason_code: str
    tool_count: int
    version_before: int | None
    version_after: int | None
    context_ref: str | None


@dataclass(frozen=True)
class TurnAssertion:
    """从同一组 ExecutionEvidence 派生的 typed assertion。"""

    sequence_id: str
    assertion_id: str
    status: Literal["passed", "failed"]


@dataclass(frozen=True)
class HarnessTurnArtifact:
    """closed-world 多轮 artifact；漏 turn、重复 execution 或缺 assertion 都不能完成。"""

    contract_version: str
    selected_sequence_ids: tuple[str, ...]
    execution_evidence: tuple[TurnExecutionEvidence, ...]
    assertions: tuple[TurnAssertion, ...]
    artifact_identity: str


class _CountingSQLTool:
    """只验证 turn 控制的本地 SQL fake。"""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = Lock()

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """计数后返回单个 SQL Tool Call，供 sequence 复用。"""

        with self._lock:
            self.calls += 1
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer="sql",
            tool_calls=(ToolCallTrace(tool_name="sql_query", status="success"),),
        )


class _CountingRAGTool:
    """只验证 turn 控制的本地 RAG fake。"""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = Lock()

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """计数后返回单个 RAG Tool Call，供 sequence 复用。"""

        with self._lock:
            self.calls += 1
        return ToolObservation(
            tool_name="rag_answer_flow", route="rag", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="answer_completed", answer="rag",
            tool_calls=(ToolCallTrace(tool_name="rag_retrieval", status="success"),),
        )


class _FakeClock:
    """TTL Eval 的可推进时钟，避免 sleep 形成脆弱测试。"""

    def __init__(self) -> None:
        self.now = datetime(2026, 8, 16, tzinfo=UTC)

    def __call__(self) -> datetime:
        """让 manager 以函数形式读取当前 fixture 时间。"""

        return self.now

    def advance(self, seconds: int) -> None:
        """确定性推进 TTL，不进行真实等待。"""

        self.now += timedelta(seconds=seconds)


def _request(question: str, *, run_id: str, owner: str = "eval-owner") -> HarnessRequest:
    """为同一 sequence 构造可信 caller；wrong-owner 只替换 owner identity。"""

    caller = demo_caller(caller_id=owner, roles=("ops",))
    return HarnessRequest(question=question, run_id=run_id, caller=caller, active_sql_role="ops")


def _evidence(sequence_id: str, turn_id: str, turn_index: int, turn: AgentTurnResult) -> TurnExecutionEvidence:
    """从唯一 turn 结果做单向投影，不重新执行 Graph/Tool。"""

    lifecycle = turn.lifecycle
    observation = turn.result.observation
    return TurnExecutionEvidence(
        sequence_id=sequence_id,
        turn_id=turn_id,
        turn_index=turn_index,
        turn_action=turn.turn_action,
        graph_invocation_count=turn.graph_invocation_count,
        route=turn.result.route,
        execution_status=turn.result.execution_status,
        answer_status=turn.result.answer_status,
        reason_code=turn.result.reason_code,
        tool_count=len(observation.tool_calls) if observation else 0,
        version_before=lifecycle.version_before if lifecycle else None,
        version_after=lifecycle.version_after if lifecycle else None,
        context_ref=lifecycle.context_ref if lifecycle else None,
    )


def _run_sequence(scenario: TurnScenario) -> list[TurnExecutionEvidence]:
    """执行一个完整 sequence；分支只是固定 fixture，不是通用对话编排器。"""

    clock = _FakeClock()
    manager = ThreadCheckpointManager(ttl_seconds=30, clock=clock)
    sql, rag = _CountingSQLTool(), _CountingRAGTool()
    runtime = HarnessRuntime(sql_tool=sql, rag_tool=rag)
    question = "退款情况怎么样？" if scenario.kind == "analytics" else "这个怎么处理？"
    initial = run_turn(
        request=TurnRequest(_request(question, run_id=f"{scenario.scenario_id}-1")),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    if initial.thread is None:  # pragma: no cover - Router 合同若回归，后续无法安全构造 resume。
        raise ValueError(f"{scenario.scenario_id} 未创建 pending thread")
    evidence = [_evidence(scenario.scenario_id, "initial", 1, initial)]
    thread_id, version = initial.thread.thread_id, initial.thread.checkpoint_version
    answers = (
        {"time_range": "2026年6月", "group_by": "渠道"}
        if scenario.kind == "analytics"
        else {"subject": "这个" if scenario.kind == "budget" else "退款政策"}
    )

    def resume(turn_id: str, *, owner: str = "eval-owner", expected: int = version) -> AgentTurnResult:
        return run_turn(
            request=TurnRequest(
                _request("补充条件", run_id=f"{scenario.scenario_id}-{turn_id}", owner=owner),
                thread_id=thread_id,
                expected_version=expected,
                clarification_answers=answers,
            ),
            runtime=runtime,
            checkpoint_manager=manager,
        )

    if scenario.kind == "wrong_owner":
        evidence.append(_evidence(scenario.scenario_id, "intruder", 2, resume("2", owner="intruder")))
        evidence.append(_evidence(scenario.scenario_id, "owner-resume", 3, resume("3")))
    elif scenario.kind == "version":
        evidence.append(_evidence(scenario.scenario_id, "stale", 2, resume("2", expected=version + 1)))
        evidence.append(_evidence(scenario.scenario_id, "owner-resume", 3, resume("3")))
    elif scenario.kind == "expiry":
        clock.advance(31)
        evidence.append(_evidence(scenario.scenario_id, "expired", 2, resume("2")))
    elif scenario.kind == "clear":
        control = clear_thread(
            thread_id=thread_id,
            expected_version=version,
            caller=_request("clear", run_id="clear-owner").caller,
            checkpoint_manager=manager,
        )
        evidence.append(
            TurnExecutionEvidence(
                sequence_id=scenario.scenario_id, turn_id="clear", turn_index=2, turn_action="clear",
                graph_invocation_count=0, route="none", execution_status="completed", answer_status="no_answer",
                reason_code=control.reason_code, tool_count=0,
                version_before=control.lifecycle.version_before, version_after=control.lifecycle.version_after,
                context_ref=None,
            )
        )
        evidence.append(_evidence(scenario.scenario_id, "after-clear", 3, resume("3", expected=version + 1)))
    elif scenario.kind == "concurrent":
        barrier = Barrier(2)

        def competing_resume(turn_id: str) -> tuple[str, AgentTurnResult]:
            barrier.wait()
            return turn_id, resume(turn_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(competing_resume, ("candidate-a", "candidate-b")))
        for index, (turn_id, turn) in enumerate(sorted(outcomes), start=2):
            evidence.append(_evidence(scenario.scenario_id, turn_id, index, turn))
    else:
        evidence.append(_evidence(scenario.scenario_id, "resume", 2, resume("2")))
    return evidence


def run_harness_turn_contracts(*, scenarios: tuple[TurnScenario, ...] = SCENARIOS) -> HarnessTurnArtifact:
    """每个 accepted turn 只执行一次 Graph，所有断言复用对应 sequence evidence。"""

    executions: list[TurnExecutionEvidence] = []
    assertions: list[TurnAssertion] = []
    for scenario in scenarios:
        sequence = _run_sequence(scenario)
        executions.extend(sequence)
        resume_turns = [item for item in sequence if item.turn_action == "resume"]
        rejected = [item for item in sequence if item.turn_action == "rejected"]
        checks = {
            "sequence_closed": [item.turn_index for item in sequence] == list(range(1, len(sequence) + 1)),
            "graph_budget": all(item.graph_invocation_count == 1 for item in sequence if item.turn_action in {"initial", "resume"})
            and all(item.graph_invocation_count == 0 for item in rejected)
            and all(item.tool_count <= 1 for item in sequence),
            # concurrent 的完成/拒绝先后不稳定；终态合同看 sequence 中是否恰好出现目标事实。
            "terminal": any(item.reason_code == scenario.expected_reason for item in sequence),
            "version_chain": sequence[0].version_after == 1
            and all(item.version_before in {None, 1} for item in sequence[1:])
            and all(item.version_after in {None, 2, 3} for item in sequence[1:]),
            "single_resume": len(resume_turns) <= 1
            and sum(item.tool_count for item in sequence) <= 1
            and (not resume_turns or resume_turns[0].context_ref is not None),
        }
        assertions.extend(
            TurnAssertion(scenario.scenario_id, assertion_id, "passed" if checks[assertion_id] else "failed")
            for assertion_id in ASSERTION_IDS
        )

    unsigned = {
        "contract_version": HARNESS_TURN_CONTRACT_VERSION,
        "selected_sequence_ids": [item.scenario_id for item in scenarios],
        "execution_evidence": [asdict(item) for item in executions],
        "assertions": [asdict(item) for item in assertions],
    }
    artifact = HarnessTurnArtifact(
        contract_version=HARNESS_TURN_CONTRACT_VERSION,
        selected_sequence_ids=tuple(item.scenario_id for item in scenarios),
        execution_evidence=tuple(executions),
        assertions=tuple(assertions),
        artifact_identity=sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
    )
    validate_completed_turn_artifact(artifact, scenarios=scenarios)
    return artifact


def validate_completed_turn_artifact(
    artifact: HarnessTurnArtifact, *, scenarios: tuple[TurnScenario, ...] = SCENARIOS
) -> None:
    """拒绝漏 sequence/turn、重复 execution、未通过或不闭合的 assertion 集。"""

    expected_ids = tuple(item.scenario_id for item in scenarios)
    if artifact.contract_version != HARNESS_TURN_CONTRACT_VERSION or artifact.selected_sequence_ids != expected_ids:
        raise ValueError("Harness turn artifact contract/sequence 不匹配")
    evidence_keys = [(item.sequence_id, item.turn_id) for item in artifact.execution_evidence]
    if len(evidence_keys) != len(set(evidence_keys)):
        raise ValueError("Harness turn execution 重复")
    if {item.sequence_id for item in artifact.execution_evidence} != set(expected_ids):
        raise ValueError("Harness turn execution 缺 sequence")
    expected_turn_counts = {
        scenario.scenario_id: 3 if scenario.kind in {"wrong_owner", "version", "clear", "concurrent"} else 2
        for scenario in scenarios
    }
    for sequence_id in expected_ids:
        indexes = [item.turn_index for item in artifact.execution_evidence if item.sequence_id == sequence_id]
        expected_indexes = list(range(1, expected_turn_counts[sequence_id] + 1))
        if indexes != expected_indexes:
            raise ValueError("Harness turn execution 缺 turn 或顺序不闭合")
    expected_assertions = [(sequence_id, assertion_id) for sequence_id in expected_ids for assertion_id in ASSERTION_IDS]
    actual_assertions = [(item.sequence_id, item.assertion_id) for item in artifact.assertions]
    if actual_assertions != expected_assertions or any(item.status != "passed" for item in artifact.assertions):
        raise ValueError("Harness turn assertion 缺失、重复或未通过")
