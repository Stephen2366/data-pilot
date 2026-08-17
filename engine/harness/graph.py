"""M35 单轮 LangGraph 顶层 Harness。

拓扑固定为 ``START → route → (sql_tool | rag_tool | terminal) → controller → END``。节点数量少
不是为了“画图”，而是每个节点都有独立的状态迁移责任：route 做选择、Tool 形成 Observation、
terminal 固化不取证停止、controller 唯一投影最终四轴。
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, replace
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from engine.harness.adapters import RAGTool, Text2SQLTool
from engine.harness.contracts import (
    AgentRunResult,
    BranchResult,
    HarnessContractError,
    HarnessRequest,
    HybridResult,
    RouteDecision,
    ToolObservation,
)
from engine.harness.hybrid import (
    DeterministicHybridSynthesizer,
    HybridSynthesisError,
    HybridSynthesizer,
    build_safe_partial_drafts,
    validate_hybrid_claims,
)
from engine.harness.router import DeterministicRouter, Router


@dataclass(frozen=True)
class HarnessRuntime:
    """一次 invoke 的非持久依赖；DB Session 和深 Tool 不进入 Graph State。"""

    sql_tool: Text2SQLTool
    rag_tool: RAGTool
    router: Router | None = None
    hybrid_synthesizer: HybridSynthesizer | None = None


class HarnessState(TypedDict, total=False):
    """只保存会随本轮迁移的事实；steps 是唯一显式 reducer 字段。"""

    request: HarnessRequest
    route_decision: RouteDecision
    observation: ToolObservation
    hybrid_sql: BranchResult
    hybrid_rag: BranchResult
    # ★ 没有并行节点，但仍显式声明 append reducer，防止将来加分支时静默覆盖审计步骤。
    graph_steps: Annotated[list[str], operator.add]
    result: AgentRunResult


def _route_node(state: HarnessState, runtime: Runtime[HarnessRuntime]) -> dict[str, Any]:
    """先拦截未解析 caller，再让 Router 只看安全的最小请求事实。"""

    request = state["request"]
    if request.caller is None:
        decision = RouteDecision("none", "caller_untrusted", False, "blocked", decision_source="controller")
    else:
        # Router interface 不接收 DB、Evidence 或正文，避免控制层反向依赖 Tool 细节。
        router: Router = runtime.context.router or DeterministicRouter()
        # M37 旧 EvidenceRef 只供同 route 深 Tool 做 validity；Router 只能看 current task，
        # 不能据旧文档/SQL identity 改 route 或把审计坐标当业务上下文。
        router_request = replace(request, follow_up_context=None) if request.follow_up_context else request
        decision = router.decide(router_request)
    return {"route_decision": decision, "graph_steps": ["route"]}


def _next_node(state: HarnessState) -> Literal["sql_tool", "rag_tool", "hybrid_sql_tool", "terminal"]:
    """把 RouteDecision 的闭集枚举映射为唯一下一跳；未知值立即合同失败。"""

    decision = state["route_decision"]
    if decision.route == "sql":
        return "sql_tool"
    if decision.route == "rag":
        return "rag_tool"
    if decision.route == "hybrid":
        return "hybrid_sql_tool"
    if decision.route == "none":
        return "terminal"
    raise HarnessContractError(f"未登记的 route edge: {decision.route}")


def _sql_tool_node(state: HarnessState, runtime: Runtime[HarnessRuntime]) -> dict[str, Any]:
    """调用一个完整的 Text2SQL Tool，而不是把其内部 pipeline 拆成顶层节点。"""

    return {"observation": runtime.context.sql_tool.run(state["request"]), "graph_steps": ["sql_tool"]}


def _rag_tool_node(state: HarnessState, runtime: Runtime[HarnessRuntime]) -> dict[str, Any]:
    """调用一个完整 RAGAnswerFlow Tool，保留既有 Gate/Composer/Validator 的唯一职责。"""

    return {"observation": runtime.context.rag_tool.run(state["request"]), "graph_steps": ["rag_tool"]}


def _hybrid_sql_tool_node(state: HarnessState, runtime: Runtime[HarnessRuntime]) -> dict[str, Any]:
    """执行 Hybrid 的第一支 SQL 深 Tool；同一 run 只换受控 branch question。"""

    plan = state["route_decision"].hybrid_plan
    if plan is None:
        raise HarnessContractError("Hybrid route 缺少 HybridPlan")
    request = replace(state["request"], question=plan.sql_question)
    observation = runtime.context.sql_tool.run_for_hybrid(request)
    return {"hybrid_sql": BranchResult("sql", observation), "graph_steps": ["hybrid_sql_tool"]}


def _hybrid_rag_tool_node(state: HarnessState, runtime: Runtime[HarnessRuntime]) -> dict[str, Any]:
    """执行 retrieval + Gate 版本的 RAG branch；绝不生成自然语言 RAG 子答案。"""

    plan = state["route_decision"].hybrid_plan
    if plan is None:
        raise HarnessContractError("Hybrid route 缺少 HybridPlan")
    request = replace(state["request"], question=plan.rag_question)
    observation = runtime.context.rag_tool.run_for_hybrid(request, requirement=plan.requirement)
    return {"hybrid_rag": BranchResult("rag", observation), "graph_steps": ["hybrid_rag_tool"]}


def _terminal_node(state: HarnessState) -> dict[str, Any]:
    """固化澄清、拒绝或 caller fail-closed 的无 Tool 终止分支。"""

    decision = state["route_decision"]
    if decision.route != "none":
        raise HarnessContractError("terminal 节点只能处理 none route")
    return {"graph_steps": ["terminal"]}


def _controller_node(state: HarnessState, runtime: Runtime[HarnessRuntime]) -> dict[str, Any]:
    """★ Harness 中唯一写最终四轴和公开终止语义的控制节点。"""

    request = state["request"]
    decision = state["route_decision"]
    observation = state.get("observation")
    steps = tuple([*state.get("graph_steps", []), "controller"])
    if decision.route == "none":
        if observation is not None:
            raise HarnessContractError("none route 不得携带 Tool Observation")
        if decision.reason_code == "caller_untrusted":
            result = AgentRunResult(
                route="none", execution_status="not_started", answer_status="no_answer", safety_status="blocked",
                reason_code="caller_untrusted", answer="当前身份未验证，无法执行查询或查阅文档。",
                route_decision=decision, observation=None, termination_action="blocked", graph_steps=steps,
                caller_safe_ref=None,
            )
        elif decision.termination_action == "clarify":
            clarification = decision.clarification_spec
            if clarification is None:
                raise HarnessContractError("clarify 决定缺少 clarification spec")
            result = AgentRunResult(
                route="none", execution_status="not_started", answer_status="clarification_required", safety_status="passed",
                reason_code=decision.reason_code, answer=clarification.prompt,
                route_decision=decision, observation=None, termination_action="clarify", graph_steps=steps,
                caller_safe_ref=request.caller.audit_ref if request.caller else None,
            )
        else:
            result = AgentRunResult(
                route="none", execution_status="not_started", answer_status="unsupported", safety_status="passed",
                reason_code=decision.reason_code, answer="当前单轮能力不支持同时汇合 SQL 与文档，或该问题不在支持范围内。",
                route_decision=decision, observation=None, termination_action="unsupported", graph_steps=steps,
                caller_safe_ref=request.caller.audit_ref if request.caller else None,
            )
        return {"result": result, "graph_steps": ["controller"]}

    if decision.route == "hybrid":
        return _hybrid_controller(state, runtime)

    if observation is None:
        raise HarnessContractError("Tool route 缺少 Observation")
    if observation.route != decision.route:
        raise HarnessContractError("Tool Observation 与 RouteDecision 不一致")
    result = AgentRunResult(
        route=decision.route,
        execution_status=observation.execution_status,
        answer_status=observation.answer_status,
        safety_status=observation.safety_status,
        reason_code=observation.reason_code,
        answer=observation.answer or "当前无法形成可公开的答案。",
        route_decision=decision,
        observation=observation,
        termination_action="answer" if observation.answer_status == "complete" else (
            "blocked" if observation.safety_status == "blocked" else "failed"
        ),
        graph_steps=steps,
        caller_safe_ref=request.caller.audit_ref if request.caller else None,
    )
    return {"result": result, "graph_steps": ["controller"]}


def _hybrid_controller(state: HarnessState, runtime: Runtime[HarnessRuntime]) -> dict[str, Any]:
    """★ 唯一 Hybrid controller：按 required branch、safety 与 validator 决定 complete/partial/stop。"""

    request = state["request"]
    decision = state["route_decision"]
    plan = decision.hybrid_plan
    sql_branch, rag_branch = state.get("hybrid_sql"), state.get("hybrid_rag")
    if plan is None or sql_branch is None or rag_branch is None:
        raise HarnessContractError("Hybrid join 缺少 plan 或 branch result")
    branches = (sql_branch, rag_branch)
    steps = tuple([*state.get("graph_steps", []), "controller"])
    # SQL 安全拦截不能被另一条文档规则淡化；明确停止且不给出跨来源建议。
    if sql_branch.observation.safety_status == "blocked":
        hybrid = HybridResult(branches=branches, reason_code="hybrid_sql_safety_blocked")
        result = AgentRunResult(
            route="hybrid", execution_status="completed", answer_status="no_answer", safety_status="blocked",
            reason_code="hybrid_sql_safety_blocked", answer="数据查询未通过安全校验，无法形成混合结论。",
            route_decision=decision, observation=None, hybrid=hybrid, termination_action="blocked", graph_steps=steps,
            caller_safe_ref=request.caller.audit_ref if request.caller else None,
        )
        return {"result": result, "graph_steps": ["controller"]}

    # 已拒绝的 Document branch 不得把 title/ref/hit 或内部原因带到 partial；只可公开另一支的
    # 已授权独立事实。实际自然语言由 Synthesizer 的 sql_partial/rag_partial operator 产生。
    if plan.conflict_fact_key is not None and sql_branch.evidence_ready and rag_branch.evidence_ready:
        hybrid = HybridResult(branches=branches, reason_code="hybrid_evidence_conflict")
        result = AgentRunResult(
            route="hybrid", execution_status="completed", answer_status="insufficient_evidence", safety_status="passed",
            reason_code="hybrid_evidence_conflict", answer="两类证据对同一事实存在冲突，当前不生成建议性结论。",
            route_decision=decision, observation=None, hybrid=hybrid, termination_action="failed", graph_steps=steps,
            caller_safe_ref=request.caller.audit_ref if request.caller else None,
        )
        return {"result": result, "graph_steps": ["controller"]}

    synthesizer = runtime.context.hybrid_synthesizer or DeterministicHybridSynthesizer()
    try:
        drafts = synthesizer.compose(plan=plan, branches=branches)
        claims, citations = validate_hybrid_claims(plan=plan, branches=branches, drafts=drafts)
    except (HybridSynthesisError, HarnessContractError):
        # ★ 不重跑任一 Tool。降级路径完全绕开失败 adapter，只从已经验证的单支 Evidence 形成
        # partial；两个分支都成功时仍只公布其中一支独立事实，绝不伪造跨来源关联。
        try:
            drafts = build_safe_partial_drafts(plan=plan, branches=branches)
            claims, citations = validate_hybrid_claims(plan=plan, branches=branches, drafts=drafts)
        except (HybridSynthesisError, HarnessContractError):
            claims, citations = (), ()
        if claims:
            hybrid = HybridResult(
                branches=branches, claims=claims, citations=citations, reason_code="hybrid_synthesizer_partial",
                synthesizer_identity=synthesizer.identity,
            )
            result = AgentRunResult(
                route="hybrid", execution_status="failed", answer_status="partial", safety_status="passed",
                reason_code="hybrid_synthesizer_partial", answer="\n\n".join(str(item["text"]) for item in claims),
                route_decision=decision, observation=None, hybrid=hybrid, termination_action="failed", graph_steps=steps,
                caller_safe_ref=request.caller.audit_ref if request.caller else None,
            )
            return {"result": result, "graph_steps": ["controller"]}
        hybrid = HybridResult(branches=branches, reason_code="hybrid_synthesizer_invalid")
        result = AgentRunResult(
            route="hybrid", execution_status="failed", answer_status="no_answer", safety_status="passed",
            reason_code="hybrid_synthesizer_invalid", answer="当前无法安全合成混合结论。",
            route_decision=decision, observation=None, hybrid=hybrid, termination_action="failed", graph_steps=steps,
            caller_safe_ref=request.caller.audit_ref if request.caller else None,
        )
        return {"result": result, "graph_steps": ["controller"]}

    if not claims:
        hybrid = HybridResult(branches=branches, reason_code="hybrid_required_evidence_unavailable")
        result = AgentRunResult(
            route="hybrid", execution_status="completed", answer_status="insufficient_evidence", safety_status="passed",
            reason_code="hybrid_required_evidence_unavailable", answer="当前缺少形成混合结论所需的证据。",
            route_decision=decision, observation=None, hybrid=hybrid, termination_action="failed", graph_steps=steps,
            caller_safe_ref=request.caller.audit_ref if request.caller else None,
        )
        return {"result": result, "graph_steps": ["controller"]}
    complete = all(branch.evidence_ready for branch in branches)
    reason = "hybrid_completed" if complete else "hybrid_safe_partial"
    hybrid = HybridResult(
        branches=branches, claims=claims, citations=citations, reason_code=reason,
        synthesizer_identity=synthesizer.identity,
    )
    result = AgentRunResult(
        route="hybrid", execution_status="completed", answer_status="complete" if complete else "partial", safety_status="passed",
        reason_code=reason, answer="\n\n".join(str(item["text"]) for item in claims), route_decision=decision,
        observation=None, hybrid=hybrid, termination_action="answer", graph_steps=steps,
        caller_safe_ref=request.caller.audit_ref if request.caller else None,
    )
    return {"result": result, "graph_steps": ["controller"]}


def build_harness() -> Any:
    """编译无 checkpoint 的固定单轮图；依赖全部在 invoke context 注入。"""

    builder = StateGraph(HarnessState, context_schema=HarnessRuntime)
    builder.add_node("route", _route_node)
    builder.add_node("sql_tool", _sql_tool_node)
    builder.add_node("rag_tool", _rag_tool_node)
    builder.add_node("hybrid_sql_tool", _hybrid_sql_tool_node)
    builder.add_node("hybrid_rag_tool", _hybrid_rag_tool_node)
    builder.add_node("terminal", _terminal_node)
    builder.add_node("controller", _controller_node)
    builder.add_edge(START, "route")
    builder.add_conditional_edges("route", _next_node, {
        "sql_tool": "sql_tool", "rag_tool": "rag_tool", "hybrid_sql_tool": "hybrid_sql_tool", "terminal": "terminal"
    })
    builder.add_edge("sql_tool", "controller")
    builder.add_edge("rag_tool", "controller")
    builder.add_edge("hybrid_sql_tool", "hybrid_rag_tool")
    builder.add_edge("hybrid_rag_tool", "controller")
    builder.add_edge("terminal", "controller")
    builder.add_edge("controller", END)
    return builder.compile()


# 应用默认复用同一份已编译拓扑；每次 invoke 仍通过 runtime context 注入独立 DB/Tool 依赖。
DEFAULT_HARNESS = build_harness()


def run_harness(*, request: HarnessRequest, runtime: HarnessRuntime) -> AgentRunResult:
    """运行一次编译图，并把 Graph/adapter 合同异常关闭为安全的结果。"""

    try:
        output = DEFAULT_HARNESS.invoke({"request": request, "graph_steps": []}, context=runtime)
        result = output.get("result")
        if not isinstance(result, AgentRunResult):
            raise HarnessContractError("compiled graph 未返回 AgentRunResult")
        return result
    except Exception as exc:  # noqa: BLE001 - 顶层不能把内部错误变成半成品答案
        decision = RouteDecision("none", "harness_contract_failure", False, "failed", decision_source="controller")
        return AgentRunResult(
            route="none", execution_status="failed", answer_status="no_answer", safety_status="passed",
            reason_code="harness_contract_failure", answer="当前请求无法安全完成，请稍后再试。",
            route_decision=decision, observation=None, termination_action="failed",
            graph_steps=("harness_contract_failure",), caller_safe_ref=request.caller.audit_ref if request.caller else None,
        )
