"""M36 turn-level Harness 测试：accepted turn 一次 Graph，前置拒绝零次。"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.agent import ToolCallTrace
from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.harness.graph import HarnessRuntime
from engine.harness.thread import ThreadCheckpointManager
from engine.harness.turn import TurnRequest, clear_thread, run_turn


def _request(question: str, *, run_id: str, caller_id: str = "owner") -> HarnessRequest:
    """构造同一 fixture caller 的多个 turn。"""

    caller = demo_caller(caller_id=caller_id, roles=("ops",))
    return HarnessRequest(question=question, run_id=run_id, caller=caller, active_sql_role="ops")


@dataclass
class FakeSQLTool:
    """计数 SQL Tool，证明一次 resume 不会重复执行。"""

    calls: int = 0

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """返回固定 SQL 完成 Observation。"""

        self.calls += 1
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="sql_completed",
            answer="sql answer",
            tool_calls=(ToolCallTrace(tool_name="sql_query", status="success"),),
        )


@dataclass
class FakeRAGTool:
    """可切换成功/不可用状态的计数 RAG Tool。"""

    calls: int = 0
    unavailable: bool = False

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """返回固定 RAG Observation，不进入真实 Knowledge/Composer。"""

        self.calls += 1
        if self.unavailable:
            return ToolObservation(
                tool_name="rag_answer_flow",
                route="rag",
                execution_status="external_unavailable",
                answer_status="no_answer",
                safety_status="passed",
                reason_code="retrieval_unavailable",
                answer="暂时无法检索",
            )
        return ToolObservation(
            tool_name="rag_answer_flow",
            route="rag",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="answer_completed",
            answer="rag answer",
        )


def test_subject_clarification_resumes_once_into_rag() -> None:
    """initial 只创建 pending，第二 turn 才调用一次 RAG 并 resolve。"""

    manager = ThreadCheckpointManager()
    sql, rag = FakeSQLTool(), FakeRAGTool()
    runtime = HarnessRuntime(sql_tool=sql, rag_tool=rag)

    initial = run_turn(
        request=TurnRequest(_request("这个怎么处理？", run_id="turn-1")),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert initial.result.answer_status == "clarification_required"
    assert initial.thread and initial.thread.status == "pending"
    assert initial.graph_invocation_count == 1
    assert sql.calls == rag.calls == 0

    resumed = run_turn(
        request=TurnRequest(
            _request("补充：退款政策", run_id="turn-2"),
            thread_id=initial.thread.thread_id,
            expected_version=initial.thread.checkpoint_version,
            clarification_answers={"subject": "退款政策"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert (resumed.result.route, resumed.result.answer_status) == ("rag", "complete")
    assert resumed.thread and (resumed.thread.status, resumed.thread.checkpoint_version) == ("resolved", 3)
    assert resumed.graph_invocation_count == 1
    assert sql.calls == 0 and rag.calls == 1

    duplicate = run_turn(
        request=TurnRequest(
            _request("重复提交", run_id="turn-3"),
            thread_id=initial.thread.thread_id,
            expected_version=initial.thread.checkpoint_version,
            clarification_answers={"subject": "退款政策"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert (duplicate.turn_action, duplicate.graph_invocation_count, duplicate.result.reason_code) == (
        "rejected",
        0,
        "thread_already_resumed",
    )
    assert rag.calls == 1


def test_analytics_clarification_resumes_once_into_sql() -> None:
    """结构化时间/维度让同一 pending task 恢复到 SQL 深 Tool。"""

    manager = ThreadCheckpointManager()
    sql, rag = FakeSQLTool(), FakeRAGTool()
    runtime = HarnessRuntime(sql_tool=sql, rag_tool=rag)
    initial = run_turn(
        request=TurnRequest(_request("退款情况怎么样？", run_id="sql-1")),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert initial.thread is not None

    resumed = run_turn(
        request=TurnRequest(
            _request("补充统计条件", run_id="sql-2"),
            thread_id=initial.thread.thread_id,
            expected_version=1,
            clarification_answers={"time_range": "2026年6月", "group_by": "渠道"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )

    assert (resumed.result.route, resumed.result.answer_status) == ("sql", "complete")
    assert sql.calls == 1 and rag.calls == 0


def test_resume_that_is_still_unclear_stops_at_budget_without_nested_pending() -> None:
    """一次补充仍含指代词时返回 budget_exhausted，不再创建第二张待办卡。"""

    manager = ThreadCheckpointManager()
    sql, rag = FakeSQLTool(), FakeRAGTool()
    runtime = HarnessRuntime(sql_tool=sql, rag_tool=rag)
    initial = run_turn(
        request=TurnRequest(_request("这个怎么处理？", run_id="budget-1")),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert initial.thread is not None

    resumed = run_turn(
        request=TurnRequest(
            _request("还是这个", run_id="budget-2"),
            thread_id=initial.thread.thread_id,
            expected_version=1,
            clarification_answers={"subject": "这个"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )

    assert (resumed.result.execution_status, resumed.result.reason_code) == ("failed", "budget_exhausted")
    assert resumed.thread and resumed.thread.status == "resolved"
    assert sql.calls == rag.calls == 0


def test_tool_unavailable_is_not_retried_and_wrong_owner_is_rejected_pre_graph() -> None:
    """Tool technical failure 沿用 M35；错误 owner 在 Graph/Tool 前停止。"""

    manager = ThreadCheckpointManager()
    sql, rag = FakeSQLTool(), FakeRAGTool(unavailable=True)
    runtime = HarnessRuntime(sql_tool=sql, rag_tool=rag)
    initial = run_turn(
        request=TurnRequest(_request("这个怎么处理？", run_id="failure-1")),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert initial.thread is not None

    intruder = run_turn(
        request=TurnRequest(
            _request("补充", run_id="failure-2", caller_id="intruder"),
            thread_id=initial.thread.thread_id,
            expected_version=1,
            clarification_answers={"subject": "退款政策"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert (intruder.turn_action, intruder.graph_invocation_count, intruder.result.safety_status) == (
        "rejected",
        0,
        "blocked",
    )
    assert rag.calls == 0

    owner = run_turn(
        request=TurnRequest(
            _request("补充", run_id="failure-3"),
            thread_id=initial.thread.thread_id,
            expected_version=1,
            clarification_answers={"subject": "退款政策"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert (owner.result.execution_status, owner.result.reason_code) == (
        "external_unavailable",
        "retrieval_unavailable",
    )
    assert rag.calls == 1


def test_explicit_clear_prevents_resume_without_graph() -> None:
    """合法 owner 清理后，同一 checkpoint 不再允许恢复。"""

    manager = ThreadCheckpointManager()
    runtime = HarnessRuntime(sql_tool=FakeSQLTool(), rag_tool=FakeRAGTool())
    initial_request = _request("这个怎么处理？", run_id="clear-1")
    initial = run_turn(
        request=TurnRequest(initial_request),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert initial.thread is not None

    cleared = clear_thread(
        thread_id=initial.thread.thread_id,
        expected_version=1,
        caller=initial_request.caller,
        checkpoint_manager=manager,
    )
    assert cleared.ok and cleared.thread and cleared.thread.status == "cleared"

    rejected = run_turn(
        request=TurnRequest(
            _request("补充", run_id="clear-2"),
            thread_id=initial.thread.thread_id,
            expected_version=cleared.thread.checkpoint_version,
            clarification_answers={"subject": "退款政策"},
        ),
        runtime=runtime,
        checkpoint_manager=manager,
    )
    assert (rejected.graph_invocation_count, rejected.result.reason_code) == (0, "thread_cleared")
