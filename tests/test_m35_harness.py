"""M35 顶层 Harness 合同测试：不访问真实模型、数据库或外部知识库。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.agent import ToolCallTrace
from engine.governance import demo_caller
from engine.harness.caller import build_default_caller_resolver
from engine.harness.contracts import HarnessRequest, RouteDecision, ToolObservation
from engine.harness.graph import HarnessRuntime, build_harness, run_harness
from engine.harness.router import DeterministicRouter


def _request(question: str, *, caller: bool = True) -> HarnessRequest:
    """构造最小可信 fixture；无 caller 用于验证 Tool 前失败关闭。"""

    trusted = demo_caller(caller_id="m35-test", roles=("ops",)) if caller else None
    return HarnessRequest(
        question=question,
        run_id="m35-test-run",
        caller=trusted,
        active_sql_role="ops" if trusted else None,
        force_new_pipeline=False,
    )


@dataclass
class FakeSQLTool:
    """可计数 SQL adapter，证明 Harness 每轮不会同时调用两个 Tool。"""

    calls: int = 0

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """模拟完成 SQL 深链，并累计调用数供独占性断言使用。"""

        self.calls += 1
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="sql_completed",
            answer="SQL answer",
            tool_calls=(ToolCallTrace(tool_name="sql_query", status="success"),),
        )


@dataclass
class FakeRAGTool:
    """可计数 RAG adapter；只返回已验证 citation 的安全投影。"""

    calls: int = 0

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """模拟完成 RAG 深链，并只交付 citation 安全投影。"""

        self.calls += 1
        return ToolObservation(
            tool_name="rag_answer_flow",
            route="rag",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="answer_completed",
            answer="RAG answer",
            citations=({"citation_id": "citation-1", "title": "退款政策"},),
            docs_used=({"citation_id": "citation-1", "title": "退款政策"},),
        )


@dataclass
class FixedRouter:
    """测试 router seam，避免通过真实规则间接验证 Graph 边。"""

    decision: RouteDecision
    calls: int = field(default=0)

    def decide(self, _request: HarnessRequest) -> RouteDecision:
        """返回预置决定，帮助测试精确覆盖 Graph conditional edge。"""

        self.calls += 1
        return self.decision


def test_graph_has_only_the_planned_single_round_nodes() -> None:
    """拓扑快照：没有 checkpoint、loop 或隐藏的第二个 controller。"""

    node_names = set(build_harness().get_graph().nodes)

    assert {"route", "sql_tool", "rag_tool", "terminal", "controller"} <= node_names
    assert "__start__" in node_names and "__end__" in node_names


def test_router_is_conservative_for_sql_rag_clarification_and_hybrid() -> None:
    """Router 只输出闭集 route；M38 只为登记的 Hybrid operator 签发薄计划。"""

    router = DeterministicRouter()

    assert router.decide(_request("各渠道订单量是多少？")).route == "sql"
    assert router.decide(_request("退款政策是什么？")).route == "rag"
    assert router.decide(_request("这个怎么处理？")).reason_code == "clarification_required"
    hybrid = router.decide(_request("查询退款率并说明退款政策"))
    assert hybrid.route == "hybrid"
    assert hybrid.hybrid_plan is not None
    assert hybrid.hybrid_plan.required_branches == ("sql", "rag")
    assert router.decide(_request("查询订单量并说明配送政策")).reason_code == "hybrid_unsupported"


def test_each_graph_route_invokes_at_most_one_tool() -> None:
    """SQL、RAG 与 terminal 三条路径均只产生其必要的调用。"""

    sql_tool, rag_tool = FakeSQLTool(), FakeRAGTool()
    runtime = HarnessRuntime(sql_tool=sql_tool, rag_tool=rag_tool)

    sql = run_harness(request=_request("各渠道订单量是多少？"), runtime=runtime)
    rag = run_harness(request=_request("退款政策是什么？"), runtime=runtime)
    none = run_harness(request=_request("请帮我预测明天销售"), runtime=runtime)

    assert (sql.route, sql.execution_status, sql.answer_status) == ("sql", "completed", "complete")
    assert (rag.route, rag.execution_status, rag.answer_status) == ("rag", "completed", "complete")
    assert (none.route, none.execution_status, none.answer_status) == ("none", "not_started", "unsupported")
    assert sql_tool.calls == 1
    assert rag_tool.calls == 1
    assert sql.graph_steps == ("route", "sql_tool", "controller")
    assert rag.graph_steps == ("route", "rag_tool", "controller")
    assert none.graph_steps == ("route", "terminal", "controller")


def test_unresolved_caller_fails_closed_before_any_tool() -> None:
    """请求体 role 无法独立授权：无 resolver 时 SQL/RAG adapter 都不能运行。"""

    sql_tool, rag_tool = FakeSQLTool(), FakeRAGTool()
    result = run_harness(
        request=_request("各渠道订单量是多少？", caller=False),
        runtime=HarnessRuntime(sql_tool=sql_tool, rag_tool=rag_tool),
    )

    assert (result.route, result.execution_status, result.answer_status, result.safety_status) == (
        "none", "not_started", "no_answer", "blocked"
    )
    assert result.reason_code == "caller_untrusted"
    assert sql_tool.calls == rag_tool.calls == 0


def test_default_caller_resolver_exists_only_for_explicit_fixture_environments() -> None:
    """G-M35-1：生产样式环境没有自动 demo 身份，未知 role 也不能被 resolver 提升。"""

    local = build_default_caller_resolver("local")

    assert local is not None
    assert local.resolve("ops") is not None
    assert local.resolve("super_admin") is None
    assert build_default_caller_resolver("production") is None
