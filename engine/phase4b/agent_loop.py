"""M44-C～E：Agent task family 的 Evidence-driven bounded Decision Loop。

外部 interface 只有 ``run_agent_loop``。Controller、LangGraph 回边、预算、Tool adapter、
EvidenceDelta、Progress、Hybrid 汇合和稳定停止都藏在 module 内部；调用方不需要学会逐节点
驱动，也不能提交 next action、预算或 knowledge runtime。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Literal, Mapping, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from engine.harness.adapters import Text2SQLTool
from engine.harness.contracts import (
    AgentRunResult,
    BranchResult,
    HarnessRequest,
    HybridPlan,
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
from engine.phase4b.b2_contracts import load_b2_contract_bundle
from engine.phase4b.b4_contracts import load_b4_contract_bundle
from engine.phase4b.comparison_completion import complete_metric_comparison
from engine.phase4b.identity import canonical_hash
from engine.phase4b.knowledge_runtime import KnowledgeRuntimeResolutionError, KnowledgeRuntimeResolver
from engine.phase4b.loop_contracts import (
    ActionAttempt,
    AgentNodeContext,
    BudgetLedger,
    BudgetProfile,
    EvidenceDelta,
    EvidenceRequirement,
    ProgressDecision,
    ResourceConsumption,
    TerminationFact,
)
from engine.phase4b.task_runtime import TaskState, attach_evidence
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import DocumentEvidencePayload

B2_BUNDLE = load_b2_contract_bundle()
B4_BUNDLE = load_b4_contract_bundle()
AGENT_LOOP_RUNTIME_IDENTITY = str(B2_BUNDLE.payload["runtime_identity"])


@dataclass(frozen=True)
class AgentLoopRuntime:
    """一次 Loop invoke 的注入依赖；adapter 不进入 TaskState。"""

    sql_tool: Text2SQLTool
    knowledge_resolver: KnowledgeRuntimeResolver
    hybrid_synthesizer: HybridSynthesizer | None = None
    # B4 只由服务端组装层开启；请求体没有也不能新增这个开关。B2 默认仍使用旧 profile。
    b4_enabled: bool = False


@dataclass(frozen=True)
class AgentLoopResult:
    """TaskState、API、Trace 与 Eval 的唯一 B2 执行事实。"""

    result: AgentRunResult
    state: TaskState
    attempts: tuple[ActionAttempt, ...]
    budget: BudgetLedger
    contexts: tuple[AgentNodeContext, ...]
    termination: TerminationFact
    knowledge_runtimes: tuple[Mapping[str, str], ...]
    runtime_identity: Mapping[str, Any]

    def safe_projection(self) -> dict[str, Any]:
        """形成 API/Trace 可共享的白名单事实，不投影深 Tool 私有 Evidence。"""

        return {
            "action_attempts": [item.safe_projection() for item in self.attempts],
            "budget": self.budget.safe_projection(),
            "termination": self.termination.safe_projection(),
            "knowledge_runtimes": [dict(item) for item in self.knowledge_runtimes],
            "runtime_identity": dict(self.runtime_identity),
        }


class _LoopState(TypedDict, total=False):
    """LangGraph 内部状态；所有可持久化事实仍由显式合同对象承载。"""

    request: HarnessRequest
    task_state: TaskState
    requirements: tuple[EvidenceRequirement, ...]
    attempts: tuple[ActionAttempt, ...]
    observations: tuple[tuple[str, ToolObservation], ...]
    covered: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    budget: BudgetLedger
    contexts: tuple[AgentNodeContext, ...]
    knowledge_runtimes: tuple[Mapping[str, str], ...]
    termination: TerminationFact
    task_context: Mapping[str, Any]


def _budget_profile(*, b4_enabled: bool = False) -> BudgetProfile:
    """按 runtime family 选择只读 B2 或 additive B4 parent profile。"""

    values = dict(B4_BUNDLE.payload["parent_budget"] if b4_enabled else B2_BUNDLE.payload["budget_profile"])
    return BudgetProfile(**values)


def _declared_cost(action_id: str, *, b4_enabled: bool = False) -> ResourceConsumption:
    """执行前保守声明本次 Action 可能占用的 hard dimensions。"""

    if action_id == "collect_document_evidence":
        if b4_enabled:
            # ★ 这是一次父 Action 的最坏 child grant，不是把 recovery 伪装成第二个顶层
            # Knowledge action。实际值仍由子图结束后的 timeline 汇总并再次守恒检查。
            return ResourceConsumption(
                actions=1, deep_tools=1, knowledge_actions=1, retrieval_batches=3,
                candidates=15, selected=3, generation_visible=3, model_calls=1,
            )
        return ResourceConsumption(
            actions=1, deep_tools=1, knowledge_actions=1, retrieval_batches=1,
            candidates=5, selected=3, generation_visible=3,
        )
    return ResourceConsumption(
        actions=1, deep_tools=1, sql_actions=1,
        repairs=1 if action_id == "repair_sql_evidence" else 0,
    )


def _dependency_status(requirement: EvidenceRequirement, observations: tuple[tuple[str, ToolObservation], ...]) -> bool | None:
    """返回依赖是否满足；None 表示还没观察，False 表示已观察但不应准入。"""

    if requirement.depends_on is None:
        return True
    if requirement.depends_on != "quality_increment_positive":
        return False
    reason_observations = [item for req_id, item in observations if "refund_reason" in req_id]
    if not reason_observations:
        return None
    observation = reason_observations[-1]
    paired_values: dict[str, float] = {}
    identity_periods = tuple(dict.fromkeys(re.findall(r"20\d{2}-(?:0[1-9]|1[0-2])", requirement.identity)))
    for row in observation.rows:
        normalized = {str(key).lower(): value for key, value in row.items()}
        reason = str(normalized.get("reason") or normalized.get("refund_reason") or normalized.get("reason_code") or "")
        if "quality" not in reason.lower() and "质量" not in reason:
            continue
        for key in ("increment", "delta", "change", "amount_delta", "net_refund_delta"):
            value = normalized.get(key)
            try:
                if value is not None and float(value) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        # ★ 真实 Text2SQL 常按“原因 × 月份”返回基础聚合，而不是替 Controller
        # 预先算好 increment。这里只消费 guarded typed rows，并且必须与 dependent
        # requirement 明示的两个月份精确对齐；缺月、坏值或无法辨认时都不解锁。
        period = str(normalized.get("month") or normalized.get("period") or "")[:7]
        amount = next(
            (
                normalized.get(key)
                for key in ("net_refund_amount", "refund_amount", "amount", "value")
                if normalized.get(key) is not None
            ),
            None,
        )
        if len(identity_periods) == 2 and period in identity_periods and amount is not None:
            try:
                paired_values[period] = paired_values.get(period, 0.0) + float(amount)
            except (TypeError, ValueError):
                return False
    if len(identity_periods) == 2 and set(paired_values) == set(identity_periods):
        return paired_values[identity_periods[1]] - paired_values[identity_periods[0]] > 0
    # deterministic oracle fake 也可显式给出安全 predicate，避免 Controller 解析答案文本。
    predicate = observation.diagnostics.get("quality_increment_positive")
    return bool(predicate) if isinstance(predicate, bool) else False


def _last_for(requirement: EvidenceRequirement, state: _LoopState) -> ToolObservation | None:
    """返回某 requirement 最近一次观察，供 bounded loop 判断能否修复。"""

    matches = [item for req_id, item in state.get("observations", ()) if req_id == requirement.identity]
    return matches[-1] if matches else None


def _repair_count(requirement: EvidenceRequirement, attempts: tuple[ActionAttempt, ...]) -> int:
    """统计同一 requirement 已消费的 SQL 修复次数，防止无界重试。"""

    return sum(
        1 for item in attempts
        if item.requirement_identity == requirement.identity and item.action_id == "repair_sql_evidence"
    )


def _choose_action(state: _LoopState) -> tuple[str, EvidenceRequirement] | None:
    """G44-2 方案 A：按 typed facts 与固定优先级选择唯一下一项 Action。"""

    covered = set(state.get("covered", ()))
    attempts = state.get("attempts", ())
    for requirement in state["requirements"]:
        if requirement.identity in covered:
            continue
        dependency = _dependency_status(requirement, state.get("observations", ()))
        if dependency is False:
            continue
        if dependency is None:
            continue
        previous = _last_for(requirement, state)
        if previous is not None:
            if (
                previous.reason_code == "sql_dialect_incompatible"
                and _repair_count(requirement, attempts) == 0
            ):
                return "repair_sql_evidence", requirement
            continue
        return (
            "collect_sql_evidence" if requirement.kind == "sql" else "collect_document_evidence",
            requirement,
        )
    return None


def _safe_observation(observation: ToolObservation, *, runtime_identity: str | None = None) -> dict[str, Any]:
    """Action ledger 的白名单 Observation；不保存 rows、正文、answer、prompt 或 raw error。"""

    allowed_diagnostics = {
        key: value
        for key, value in observation.diagnostics.items()
        if key in {
            "runtime_identity", "knowledge_runtime_kind", "release_identity", "corpus_identity",
            "retrieval_adapter_identity", "retrieval_recipe_identity", "authorization_policy_identity",
            "outbound_policy_identity", "knowledge_tool_calls", "composer_calls", "candidate_count",
            "selected_count", "context_count", "quality_increment_positive", "issue_code",
            "hybrid_rag_mode", "provider_usage",
            "b4_subgraph", "acquisition_strategy_identity",
        }
    }
    if runtime_identity is not None:
        allowed_diagnostics["resolved_runtime_identity"] = runtime_identity
    return {
        "tool_name": observation.tool_name, "route": observation.route,
        "execution_status": observation.execution_status, "answer_status": observation.answer_status,
        "safety_status": observation.safety_status, "reason_code": observation.reason_code,
        "error_type": observation.error_type, "evidence_refs": list(observation.evidence_refs),
        "diagnostics": allowed_diagnostics,
    }


def _stage_counts(observation: ToolObservation) -> tuple[int, int, int]:
    """从安全 ledger 投影汇总候选、入选和生成可见 Evidence 数量。"""

    ledger = observation.ledger_projection or {}
    entries = ledger.get("evidence", []) if isinstance(ledger, dict) else []
    if not isinstance(entries, list):
        return 0, 0, 0
    stages = [item.get("stage") for item in entries if isinstance(item, dict)]
    return len(stages), sum(stage in {"selected", "generation_visible", "cited"} for stage in stages), sum(
        stage in {"generation_visible", "cited"} for stage in stages
    )


def _consumption(observation: ToolObservation, *, action_id: str) -> ResourceConsumption:
    """把异构 diagnostics/Trace 收敛为统一 consumption；未知 token 明确 not-observed。"""

    model_calls = 0
    total_tokens = 0
    token_observed = True
    for step in observation.trace_steps:
        call = step.metadata.get("llm_call") if isinstance(step.metadata, dict) else None
        if not isinstance(call, dict):
            continue
        model_calls += int(call.get("attempt_count", 0) or 0)
        usage = call.get("usage")
        if isinstance(usage, dict) and usage.get("observed") is True:
            total_tokens += int(usage.get("total_tokens", 0) or 0)
        else:
            token_observed = False
    provider_usage = observation.diagnostics.get("provider_usage")
    if isinstance(provider_usage, dict):
        model_calls += int(provider_usage.get("request_count", 0) or 0)
        if "total_tokens" in provider_usage:
            total_tokens += int(provider_usage.get("total_tokens", 0) or 0)
        else:
            token_observed = False
    candidates, selected, generation_visible, batches = (0, 0, 0, 0)
    if observation.route == "rag":
        batches = 1
        candidates, selected, generation_visible = _stage_counts(observation)
        candidates = int(observation.diagnostics.get("candidate_count", candidates) or candidates)
        selected = int(observation.diagnostics.get("selected_count", selected) or selected)
        generation_visible = int(observation.diagnostics.get("context_count", generation_visible) or generation_visible)
        # B4 的实际 child ledger 来自同一 acquisition facts。这里仅把可与父账守恒的数字
        # 汇总进旧 ResourceConsumption；完整 child timeline 仍留在安全 Observation，供 v4
        # artifact 投影，不能靠反向解析 answer 或 Trace 猜测。
        b4 = observation.diagnostics.get("b4_subgraph")
        if isinstance(b4, dict) and isinstance(b4.get("consumption"), dict):
            child = b4["consumption"]
            batches = int(child.get("initial_retrieval_batches", 0) or 0) + int(
                child.get("rewrite_retrieval_batches", 0) or 0
            )
            candidates = int(child.get("candidates_examined", candidates) or candidates)
            selected = int(child.get("selected", selected) or selected)
            generation_visible = int(child.get("generation_visible", generation_visible) or generation_visible)
            model_calls = int(child.get("model_calls", model_calls) or model_calls)
            total_tokens = int(child.get("total_tokens", total_tokens) or total_tokens)
            token_observed = bool(child.get("token_usage_observed", token_observed))
    latency = sum(float(call.latency_ms) for call in observation.tool_calls)
    timeout = int("timeout" in str(observation.error_type or observation.reason_code).lower())
    return ResourceConsumption(
        actions=1, deep_tools=1,
        sql_actions=1 if observation.route == "sql" else 0,
        knowledge_actions=1 if observation.route == "rag" else 0,
        repairs=1 if action_id == "repair_sql_evidence" else 0,
        retrieval_batches=batches if observation.route == "rag" else 0,
        candidates=candidates, selected=selected, generation_visible=generation_visible,
        model_calls=model_calls, total_tokens=total_tokens,
        token_usage_observed=token_observed, timeouts=timeout, latency_ms=round(latency, 3),
    )


def _document_keys(observation: ToolObservation) -> set[str]:
    """仅在进程内从 Gate-visible typed Evidence 判断文档 requirement coverage。"""

    keys: set[str] = set()
    for evidence in observation.raw_evidence:
        if isinstance(evidence.payload, DocumentEvidencePayload):
            keys.add(evidence.payload.document_key)
    return keys


def _requirement_covered(requirement: EvidenceRequirement, observation: ToolObservation) -> bool:
    """只依据 typed Observation 判断单项 requirement 是否真正闭合。"""

    if observation.execution_status != "completed" or observation.safety_status != "passed":
        return False
    if requirement.kind == "sql":
        return bool(observation.evidence_refs)
    if requirement.expected_document_keys:
        return set(requirement.expected_document_keys) <= _document_keys(observation)
    return bool(observation.evidence_refs)


def _has_future_action(state: _LoopState) -> bool:
    """判断当前状态是否仍存在一项合法且未消费的后续 Action。"""

    return _choose_action(state) is not None


def _termination(
    reason: str,
    detail: str,
    requirements: tuple[EvidenceRequirement, ...],
    covered: tuple[str, ...],
    observations: tuple[tuple[str, ToolObservation], ...] = (),
) -> TerminationFact:
    """构造稳定的终止事实，并区分 active 与 unresolved requirements。"""

    active = tuple(
        item.identity for item in requirements
        if _dependency_status(item, observations) is not False
    )
    unresolved = tuple(item.identity for item in requirements if item.identity not in set(covered))
    return TerminationFact(reason, detail, active, unresolved)  # type: ignore[arg-type]


def _step_node(state: _LoopState, runtime: Runtime[AgentLoopRuntime]) -> dict[str, Any]:
    """一次节点只执行一个 Action；conditional edge 再回到本节点重新决策。"""

    choice = _choose_action(state)
    requirements = state["requirements"]
    covered = state.get("covered", ())
    if choice is None:
        dependent_unneeded = all(
            item.identity in set(covered) or _dependency_status(item, state.get("observations", ())) is False
            for item in requirements
        )
        reason = "answer_ready" if dependent_unneeded else "no_progress"
        return {"termination": _termination(reason, reason, requirements, covered, state.get("observations", ()))}
    action_id, requirement = choice
    attempts = state.get("attempts", ())
    ledger = state["budget"]
    declared = _declared_cost(action_id, b4_enabled=runtime.context.b4_enabled)
    if not ledger.allows(declared, repair_count_for_requirement=_repair_count(requirement, attempts)):
        return {"termination": _termination(
            "budget_exhausted", "next_action_precheck", requirements, covered, state.get("observations", ())
        )}

    input_fingerprint = canonical_hash({
        "action_id": action_id, "requirement": requirement.safe_projection(),
        "task_state_identity": state["task_state"].identity,
    })
    duplicate_key = canonical_hash({
        "action_id": action_id, "requirement_identity": requirement.identity,
        "input_fingerprint": input_fingerprint,
    })
    if duplicate_key in set(state.get("duplicate_keys", ())):
        return {"termination": _termination(
            "no_progress", "duplicate_action", requirements, covered, state.get("observations", ())
        )}

    request = replace(state["request"], question=requirement.query, follow_up_context=None)
    resolved_runtime: Mapping[str, str] | None = None
    try:
        if action_id == "collect_document_evidence":
            resolution = runtime.context.knowledge_resolver.resolve(
                requirement=requirement, caller=request.caller
            )
            resolved_runtime = resolution.safe_projection()
            rag_requirement = AnswerEvidenceRequirement(
                min_evidence=max(1, len(requirement.expected_document_keys)),
                required_document_keys=requirement.expected_document_keys,
                max_claims=3,
            )
            observation = resolution.adapter.run_for_hybrid(request, requirement=rag_requirement)
        elif action_id == "repair_sql_evidence":
            previous = _last_for(requirement, state)
            repair = getattr(runtime.context.sql_tool, "run_repair", None)
            if previous is None or repair is None or previous.sql_repair_snapshot is None:
                raise RuntimeError("sql_repair_adapter_unavailable")
            observation = repair(request, snapshot=previous.sql_repair_snapshot)
        else:
            observation = runtime.context.sql_tool.run_for_hybrid(request)
    except KnowledgeRuntimeResolutionError as exc:
        observation = ToolObservation(
            tool_name="rag_evidence_gate", route="rag", execution_status="external_unavailable",
            answer_status="no_answer", safety_status="passed", reason_code=exc.reason_code,
            error_type=exc.reason_code, diagnostics={"knowledge_runtime_kind": requirement.runtime_scope},
        )
    except Exception:  # noqa: BLE001 - adapter exception 关闭为 typed failure，绝不生成半答案
        route: Literal["sql", "rag"] = "rag" if requirement.kind == "document" else "sql"
        observation = ToolObservation(
            tool_name="rag_evidence_gate" if route == "rag" else "text2sql", route=route,
            execution_status="failed", answer_status="no_answer", safety_status="passed",
            reason_code="action_adapter_failure", error_type="action_adapter_failure",
        )

    actual = _consumption(observation, action_id=action_id)
    before = ledger.safe_projection()
    actual_overrun = False
    try:
        after_ledger = ledger.consume(actual)
    except ValueError:
        # 调用已经真实发生，不能把它从账本抹掉。保留超额 actual consumption 并立即停止；
        # 下一动作永远不会在超额账本上获准。
        after_ledger = BudgetLedger(ledger.profile, ledger.consumed.add(actual))
        actual_overrun = True
    existing_ids = {
        str(item.ref.get("evidence_id")) for item in state["task_state"].evidence if item.validity == "active"
    }
    new_refs = tuple(ref for ref in observation.evidence_refs if str(ref.get("evidence_id")) not in existing_ids)
    duplicates = tuple(
        str(ref.get("evidence_id")) for ref in observation.evidence_refs if str(ref.get("evidence_id")) in existing_ids
    )
    delta = EvidenceDelta(added=new_refs, duplicate=duplicates)
    is_covered = _requirement_covered(requirement, observation)
    next_covered = tuple(dict.fromkeys((*covered, *((requirement.identity,) if is_covered else ()))))
    next_task_state = attach_evidence(
        state["task_state"], new_refs, requirement_identity=requirement.identity,
        action_id=action_id, input_fingerprint=input_fingerprint,
        runtime_identity=resolved_runtime.get("runtime_identity") if resolved_runtime else None,
    )
    provisional: _LoopState = {
        **state, "task_state": next_task_state,
        "covered": next_covered,
        "observations": (*state.get("observations", ()), (requirement.identity, observation)),
        "budget": after_ledger,
    }
    eligible_remains = _has_future_action(provisional)
    progress = ProgressDecision(
        coverage_increased=delta.gained,
        eligible_action_remains=eligible_remains,
        reason_code="coverage_increased" if delta.gained else (
            "recoverable_observation" if eligible_remains else "no_evidence_gain"
        ),
    )
    status = (
        "blocked" if observation.safety_status == "blocked" else
        "external_unavailable" if observation.execution_status == "external_unavailable" else
        "completed" if observation.execution_status == "completed" else "failed"
    )
    attempt = ActionAttempt(
        len(attempts) + 1, action_id, requirement.identity, input_fingerprint, duplicate_key, status,
        _safe_observation(
            observation,
            runtime_identity=resolved_runtime.get("runtime_identity") if resolved_runtime else None,
        ),
        before, actual, after_ledger.safe_projection(), delta, progress,
    )
    context_payload = {
        "action_id": action_id, "requirement_identity": requirement.identity,
        "input_fingerprint": input_fingerprint, "budget_before_identity": canonical_hash(before),
        "runtime_scope": requirement.runtime_scope,
    }
    if state.get("task_context"):
        context_payload["task_context"] = state["task_context"]
    context = AgentNodeContext(
        "document_action" if requirement.kind == "document" else "sql_action",
        (state["task_state"].identity, requirement.identity),
        context_payload, tuple(context_payload), len(context_payload), 512,
    )
    output: dict[str, Any] = {
        "task_state": next_task_state,
        "attempts": (*attempts, attempt),
        "observations": provisional["observations"],
        "covered": next_covered,
        "duplicate_keys": (*state.get("duplicate_keys", ()), duplicate_key),
        "budget": after_ledger,
        "contexts": (*state.get("contexts", ()), context),
        "knowledge_runtimes": (
            *state.get("knowledge_runtimes", ()), *((resolved_runtime,) if resolved_runtime else ())
        ),
    }
    if actual_overrun:
        output["termination"] = _termination(
            "budget_exhausted", "actual_consumption_exceeded", requirements, next_covered,
            provisional["observations"],
        )
    elif observation.safety_status == "blocked":
        output["termination"] = _termination(
            "unsafe", observation.reason_code, requirements, next_covered, provisional["observations"]
        )
    elif observation.execution_status == "external_unavailable":
        output["termination"] = _termination(
            "external_unavailable", observation.reason_code, requirements, next_covered, provisional["observations"]
        )
    elif observation.execution_status == "failed" and not eligible_remains:
        output["termination"] = _termination(
            "unrecoverable", observation.reason_code, requirements, next_covered, provisional["observations"]
        )
    elif requirement.kind == "document" and not is_covered and not eligible_remains:
        # Document 即使新增了部分 Evidence，只要 required key 未闭合且唯一 Knowledge action
        # 已消费，也必须稳定停止；不得重复同一 query 假装 recovery。
        output["termination"] = _termination(
            "budget_exhausted", "required_coverage_incomplete", requirements, next_covered,
            provisional["observations"],
        )
    elif not delta.gained and not eligible_remains:
        output["termination"] = _termination(
            "no_progress", "required_coverage_incomplete", requirements, next_covered,
            provisional["observations"],
        )
    return output


def _continue_or_end(state: _LoopState) -> Literal["step", "end"]:
    """LangGraph 条件边：一旦生成 termination 就结束，否则继续一步。"""

    return "end" if "termination" in state else "step"


def build_agent_loop() -> Any:
    """编译 agent-family 独立循环；framework recursion limit 只作实现缺陷保险。"""

    builder = StateGraph(_LoopState, context_schema=AgentLoopRuntime)
    builder.add_node("step", _step_node)
    builder.add_edge(START, "step")
    builder.add_conditional_edges("step", _continue_or_end, {"step": "step", "end": END})
    return builder.compile()


DEFAULT_AGENT_LOOP = build_agent_loop()


def _hybrid_result(
    *,
    request: HarnessRequest,
    observations: tuple[tuple[str, ToolObservation], ...],
    synthesizer: HybridSynthesizer | None,
    termination: TerminationFact,
) -> AgentRunResult:
    """复用唯一 Hybrid synthesizer/validator，从本轮两类 typed Evidence 汇合答案。"""

    sql = next((item for _, item in observations if item.route == "sql" and item.raw_evidence), None)
    rag = next((item for _, item in observations if item.route == "rag"), None)
    if sql is None:
        sql = next((item for _, item in observations if item.route == "sql"), None)
    if rag is None:
        rag = ToolObservation(
            tool_name="rag_evidence_gate", route="rag", execution_status="failed",
            answer_status="no_answer", safety_status="passed", reason_code="document_evidence_missing",
            error_type="document_evidence_missing",
        )
    if sql is None:
        sql = ToolObservation(
            tool_name="text2sql", route="sql", execution_status="failed", answer_status="no_answer",
            safety_status="passed", reason_code="sql_evidence_missing", error_type="sql_evidence_missing",
        )
    branches = (BranchResult("sql", sql), BranchResult("rag", rag))
    requirement = AnswerEvidenceRequirement(
        min_evidence=2,
        required_document_keys=("refund_policy_basic", "refund_policy_quality"),
        max_claims=3,
    )
    plan = HybridPlan(
        identity="refund-change-and-policy-v1", operator="refund_change_and_policy",
        sql_question="由 typed requirement 提供", rag_question="由 typed requirement 提供",
        requirement=requirement,
    )
    decision = RouteDecision("hybrid", "phase4b_agent_hybrid", True, "answer", hybrid_plan=plan)
    active = synthesizer or DeterministicHybridSynthesizer()
    try:
        drafts = active.compose(plan=plan, branches=branches)
        claims, citations = validate_hybrid_claims(plan=plan, branches=branches, drafts=drafts)
    except (HybridSynthesisError, ValueError):
        try:
            drafts = build_safe_partial_drafts(plan=plan, branches=branches)
            claims, citations = validate_hybrid_claims(plan=plan, branches=branches, drafts=drafts)
        except (HybridSynthesisError, ValueError):
            claims, citations = (), ()
    complete = all(branch.evidence_ready for branch in branches) and termination.reason == "answer_ready"
    answer_status = "complete" if complete else ("partial" if claims else "insufficient_evidence")
    answer = "\n\n".join(str(item["text"]) for item in claims) if claims else "当前缺少形成混合结论所需的证据。"
    hybrid = HybridResult(
        branches=branches, claims=claims, citations=citations,
        reason_code="hybrid_completed" if complete else "hybrid_required_evidence_unavailable",
        synthesizer_identity=active.identity,
    )
    safety = "blocked" if termination.reason == "unsafe" else "passed"
    execution = "external_unavailable" if termination.reason == "external_unavailable" else (
        "failed" if termination.reason in {"unrecoverable", "agent_loop_contract_failure"} else "completed"
    )
    return AgentRunResult(
        route="hybrid", execution_status=execution, answer_status=answer_status, safety_status=safety,
        reason_code=termination.detail_code, answer=answer, route_decision=decision, observation=None,
        termination_action="blocked" if safety == "blocked" else ("answer" if claims else "failed"),
        graph_steps=("agent_decision_loop", "hybrid_synthesis", "controller"),
        caller_safe_ref=request.caller.audit_ref if request.caller else None, hybrid=hybrid,
    )


def _single_route_result(
    *, request: HarnessRequest, observations: tuple[tuple[str, ToolObservation], ...], termination: TerminationFact
) -> AgentRunResult:
    """SQL-only turn 保留最后 Observation 的兼容 rows，并把多动作答案安全串联。"""

    observation = observations[-1][1] if observations else None
    if observation is None:
        decision = RouteDecision("none", termination.detail_code, False, "failed", decision_source="controller")
        return AgentRunResult(
            "none", "failed", "no_answer", "passed", termination.detail_code,
            "当前请求无法安全完成。", decision, None, "failed", ("agent_decision_loop", "controller"),
            request.caller.audit_ref if request.caller else None,
        )
    decision = RouteDecision(observation.route, "phase4b_agent_loop", True, "answer")
    answers = tuple(item.answer for _, item in observations if item.answer)
    answer = "\n\n".join(dict.fromkeys(answers)) or "当前无法形成可公开的答案。"
    return AgentRunResult(
        route=observation.route, execution_status=observation.execution_status,
        answer_status=observation.answer_status if termination.reason == "answer_ready" else (
            "partial" if observation.evidence_refs else "no_answer"
        ),
        safety_status=observation.safety_status, reason_code=termination.detail_code, answer=answer,
        route_decision=decision, observation=observation,
        termination_action="blocked" if observation.safety_status == "blocked" else (
            "answer" if observation.evidence_refs else "failed"
        ),
        graph_steps=("agent_decision_loop", "controller"),
        caller_safe_ref=request.caller.audit_ref if request.caller else None,
    )


def _complete_comparison_if_required(
    *, state: TaskState, observations: tuple[tuple[str, ToolObservation], ...],
    termination: TerminationFact, covered: tuple[str, ...],
) -> tuple[tuple[tuple[str, ToolObservation], ...], TerminationFact, Mapping[str, Any]]:
    """在 answer_ready 前闭合 typed 两期比较；非比较任务完全旁路。"""

    comparison_requirements = tuple(
        item for item in state.evidence_requirements
        if item.kind == "sql" and item.purpose == "metric_comparison"
    )
    constraints = dict(state.constraints)
    periods = tuple(constraints.get("periods", ()))
    if not comparison_requirements or len(periods) == 1:
        return observations, termination, {"status": "not_applicable"}
    if len(comparison_requirements) != 1:
        stopped = _termination(
            "no_progress", "comparison_requirement_ambiguous",
            state.evidence_requirements, covered, observations,
        )
        return observations, stopped, {"status": "blocked", "reason_code": stopped.detail_code}

    requirement = comparison_requirements[0]
    matches = [
        (index, observation) for index, (requirement_id, observation) in enumerate(observations)
        if requirement_id == requirement.identity
    ]
    # 后续 turn 没改 metric/periods 时，主 comparison Evidence 会作为 active durable
    # coverage 进入 covered。此时本轮应专注新增 requirement，不能强迫重复查 SQL；
    # 但凡本轮真的重查过 comparison，仍继续走下面的唯一成功 Observation 严格校验。
    if not matches and requirement.identity in set(covered):
        return observations, termination, {
            "status": "already_covered", "reason_code": "comparison_evidence_already_covered",
        }
    # 同一 requirement 经过 allowlisted repair 时会合法留下两条 Observation：首次
    # dialect failure 与 repair success。比较完成只能消费唯一成功且安全的那一条；
    # 不能因为账本保留了失败历史，就把真实成功结果误报为“没有 Observation”。
    successful_matches = [
        (index, observation) for index, observation in matches
        if observation.execution_status == "completed" and observation.safety_status == "passed"
    ]
    if len(successful_matches) != 1:
        stopped = _termination(
            "no_progress", "comparison_observation_missing",
            state.evidence_requirements, covered, observations,
        )
        return observations, stopped, {"status": "blocked", "reason_code": stopped.detail_code}

    index, observation = successful_matches[0]
    completion = complete_metric_comparison(
        requirement=requirement, constraints=constraints, observation=observation,
    )
    if completion.status == "complete":
        updated = list(observations)
        updated[index] = (requirement.identity, completion.observation)
        return tuple(updated), termination, {
            "status": "complete", "reason_code": completion.reason_code,
            "identity": completion.fact.identity if completion.fact else None,
        }
    if completion.status == "not_applicable":
        return observations, termination, {"status": "not_applicable"}
    stopped = _termination(
        "no_progress", completion.reason_code,
        state.evidence_requirements, covered, observations,
    )
    return observations, stopped, {"status": "blocked", "reason_code": completion.reason_code}


def run_agent_loop(
    *, request: HarnessRequest, state: TaskState, runtime: AgentLoopRuntime,
    task_context: Mapping[str, Any] | None = None,
) -> AgentLoopResult:
    """运行一次编译图并返回同源事实；业务停止应先于 recursion limit。"""

    decision_payload = {
        "requirement_identities": [item.identity for item in state.evidence_requirements],
        "active_evidence_ids": [item.ref.get("evidence_id") for item in state.evidence if item.validity == "active"],
        "budget_profile_identity": _budget_profile(b4_enabled=runtime.b4_enabled).identity,
        "controller_identity": "phase4b-deterministic-controller-v1",
    }
    if task_context:
        decision_payload["task_context"] = dict(task_context)
    decision_context = AgentNodeContext(
        "decision", (state.identity,),
        decision_payload, tuple(decision_payload), len(decision_payload), 768,
    )
    initial: _LoopState = {
        "request": request, "task_state": state, "requirements": state.evidence_requirements,
        "attempts": (), "observations": (),
        # 跨 turn 只信任 TaskState 中仍 active 的 EvidenceRef；它们覆盖旧 requirement，
        # 但不会进入当前 Synthesizer（freshness=current_run 的新 requirement 仍需重查）。
        "covered": tuple(dict.fromkeys(
            item.requirement_identity for item in state.evidence if item.validity == "active"
        )),
        "duplicate_keys": (),
        "budget": BudgetLedger(_budget_profile(b4_enabled=runtime.b4_enabled)), "contexts": (decision_context,),
        "knowledge_runtimes": (),
        "task_context": dict(task_context) if task_context else {},
    }
    try:
        output = DEFAULT_AGENT_LOOP.invoke(initial, context=runtime, config={"recursion_limit": 12})
        termination = output.get("termination")
        if not isinstance(termination, TerminationFact):
            raise ValueError("agent_loop_termination_missing")
    except Exception:  # noqa: BLE001 - Graph/contract 异常统一失败关闭
        termination = _termination(
            "agent_loop_contract_failure", "agent_loop_contract_failure", state.evidence_requirements, ()
        )
        output = {**initial, "termination": termination}
    observations = tuple(output.get("observations", ()))
    _comparison_projection: Mapping[str, Any] = {"status": "not_applicable"}
    if state.route == "sql":
        observations, termination, _comparison_projection = _complete_comparison_if_required(
            state=state, observations=observations, termination=termination,
            covered=tuple(output.get("covered", ())),
        )
    if state.route == "hybrid":
        result = _hybrid_result(
            request=request, observations=observations,
            synthesizer=runtime.hybrid_synthesizer, termination=termination,
        )
    else:
        result = _single_route_result(request=request, observations=observations, termination=termination)
    attempts = tuple(output.get("attempts", ()))
    budget = output.get("budget", initial["budget"])
    contexts = tuple(output.get("contexts", ()))
    if state.route == "hybrid":
        visible_refs = [
            str(ref.get("evidence_id"))
            for _requirement_id, observation in observations
            for ref in observation.evidence_refs
            if observation.safety_status == "passed"
        ]
        synthesis_payload = {
            "evidence_ids": visible_refs,
            "termination_reason": termination.reason,
            "synthesizer_identity": (runtime.hybrid_synthesizer or DeterministicHybridSynthesizer()).identity,
        }
        if task_context:
            synthesis_payload["task_context"] = dict(task_context)
        contexts = (*contexts, AgentNodeContext(
            "hybrid_synthesis",
            tuple(item.requirement_identity for item in attempts),
            synthesis_payload, tuple(synthesis_payload), len(synthesis_payload), 768,
        ))
    controller_payload = {
        "termination": termination.safe_projection(), "action_count": len(attempts),
        "budget_identity": canonical_hash(budget.safe_projection()), "route": result.route,
    }
    if task_context:
        controller_payload["task_context"] = dict(task_context)
    contexts = contexts + (
        AgentNodeContext(
            "controller_response", (output.get("task_state", state).identity,),
            controller_payload, tuple(controller_payload), len(controller_payload), 768,
        ),
    )
    committed = replace(
        output.get("task_state", state), termination=termination.reason,
        last_action_attempts=tuple(item.safe_projection() for item in attempts),
        last_budget=budget.safe_projection(), last_termination=termination.safe_projection(),
    )
    runtime_identity = {
        "format": str(B4_BUNDLE.payload["runtime_identity"]) if runtime.b4_enabled else AGENT_LOOP_RUNTIME_IDENTITY,
        "contract_identity": B4_BUNDLE.content_identity if runtime.b4_enabled else B2_BUNDLE.content_identity,
        "task_state_version": committed.state_version,
        "controller_identity": "phase4b-deterministic-controller-v1",
        "budget_profile_identity": budget.profile.identity,
        "knowledge_resolver_identity": runtime.knowledge_resolver.identity,
        "b4_enabled": runtime.b4_enabled,
    }
    return AgentLoopResult(
        result, committed, attempts, budget, contexts, termination,
        tuple(output.get("knowledge_runtimes", ())), runtime_identity,
    )
