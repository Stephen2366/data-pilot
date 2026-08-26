"""M43-B/D：TaskDelta → TaskState 的纯状态机与白名单节点上下文。

★ 业务字段只作为通用 ``constraints`` 项出现；退款/月/channel 都不是 TaskState 顶层字段。
调用者只需使用 ``understand_turn``、``apply_delta`` 和 ``project_node_contexts`` 三个深接口。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping

from engine.phase4b.b1_contracts import load_b1_contract_bundle
from engine.phase4b.identity import canonical_hash
from engine.phase4b.loop_contracts import EvidenceRequirement

DeltaCategory = Literal["start_task", "continue", "modify_constraint", "ask_about_existing_result", "add_evidence_requirement", "switch_task", "correct_previous_understanding", "cancel"]
TaskStatus = Literal["active", "clarification_required", "cancelled", "switched", "cleared"]

TASK_STATE_VERSION = "phase4b-task-state-v2"
DELTA_CATEGORIES = {"start_task", "continue", "modify_constraint", "ask_about_existing_result", "add_evidence_requirement", "switch_task", "correct_previous_understanding", "cancel"}
_B1_BUNDLE = load_b1_contract_bundle()
B1_CONTRACT_IDENTITY = _B1_BUNDLE.content_identity
_B1_VOCABULARY = _B1_BUNDLE.payload["vocabulary"]


@dataclass(frozen=True)
class TaskDelta:
    """确定性理解产出的 closed-world 增量；客户端不能直接构造它。"""

    category: DeltaCategory
    goal: str | None = None
    set_constraints: tuple[tuple[str, Any], ...] = ()
    remove_constraints: tuple[str, ...] = ()
    add_requirements: tuple[str, ...] = ()
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    route: Literal["sql", "rag", "hybrid", "none"] | None = None
    pending_questions: tuple[str, ...] = ()
    source_identity: str = "phase4b-deterministic-turn-understanding-v1"

    def __post_init__(self) -> None:
        if self.category not in DELTA_CATEGORIES:
            raise ValueError("task_delta_category_invalid")
        keys = [key for key, _ in self.set_constraints]
        if len(keys) != len(set(keys)) or set(keys) & set(self.remove_constraints):
            raise ValueError("task_delta_constraints_invalid")

    def safe_projection(self) -> dict[str, Any]:
        return {
            "category": self.category, "goal": self.goal, "set_constraints": dict(self.set_constraints),
            "remove_constraints": list(self.remove_constraints), "add_requirements": list(self.add_requirements),
            "evidence_requirements": [item.safe_projection() for item in self.evidence_requirements],
            "route": self.route, "pending_questions": list(self.pending_questions),
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True)
class TaskEvidence:
    """只保存可审计引用和 validity，不长期保存 rows、正文或答案。"""

    ref: Mapping[str, Any]
    route: str
    requirement_identity: str
    validity: Literal["active", "invalidated", "denied", "revoked", "stale"] = "active"
    invalidation_reason: str | None = None
    source_generation: int = 1
    action_id: str | None = None
    input_fingerprint: str | None = None
    runtime_identity: str | None = None

    def safe_projection(self) -> dict[str, Any]:
        return {
            "ref": dict(self.ref), "route": self.route, "requirement_identity": self.requirement_identity,
            "validity": self.validity, "invalidation_reason": self.invalidation_reason,
            "source_generation": self.source_generation, "action_id": self.action_id,
            "input_fingerprint": self.input_fingerprint, "runtime_identity": self.runtime_identity,
        }


@dataclass(frozen=True)
class TaskState:
    """跨 turn 的最小通用任务事实；owner_ref 是不可逆内部绑定。"""

    owner_ref: str
    generation: int = 1
    status: TaskStatus = "active"
    goal: str = ""
    constraints: tuple[tuple[str, Any], ...] = ()
    pending_questions: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()
    route: Literal["sql", "rag", "hybrid", "none"] = "none"
    evidence: tuple[TaskEvidence, ...] = ()
    termination: str | None = None
    last_action_attempts: tuple[Mapping[str, Any], ...] = ()
    last_budget: Mapping[str, Any] | None = None
    last_termination: Mapping[str, Any] | None = None
    state_version: str = TASK_STATE_VERSION

    def __post_init__(self) -> None:
        """规范化 JSON array 型 constraint，保证 MySQL restart 前后 Python 语义一致。

        ★ JSON 没有 tuple；如果只在 decode 端修复，直接构造的测试/调用方仍会分叉。
        因此在 TaskState 的唯一值对象入口把 list 递归冻结为 tuple。该规范化不改变
        ``safe_projection`` 的 canonical JSON，也不改签 TaskState v2 identity。
        """

        def freeze(value: Any) -> Any:
            if isinstance(value, list):
                return tuple(freeze(item) for item in value)
            if isinstance(value, tuple):
                return tuple(freeze(item) for item in value)
            return value

        object.__setattr__(self, "constraints", tuple((key, freeze(value)) for key, value in self.constraints))

    @property
    def identity(self) -> str:
        return canonical_hash(self.safe_projection())

    def safe_projection(self) -> dict[str, Any]:
        return {
            "state_version": self.state_version, "generation": self.generation, "status": self.status,
            "goal": self.goal, "constraints": dict(self.constraints),
            "pending_questions": list(self.pending_questions), "requirements": list(self.requirements),
            "evidence_requirements": [item.safe_projection() for item in self.evidence_requirements],
            "route": self.route, "evidence": [item.safe_projection() for item in self.evidence],
            "termination": self.termination, "last_action_attempts": [dict(item) for item in self.last_action_attempts],
            "last_budget": dict(self.last_budget) if self.last_budget is not None else None,
            "last_termination": dict(self.last_termination) if self.last_termination is not None else None,
        }


@dataclass(frozen=True)
class TaskTransition:
    """API/Trace/Eval 共用的状态转换事实。"""

    category: DeltaCategory
    before_identity: str | None
    after_identity: str
    changed_fields: tuple[str, ...]
    invalidated_evidence_count: int

    def safe_projection(self) -> dict[str, Any]:
        return {"category": self.category, "before_identity": self.before_identity, "after_identity": self.after_identity, "changed_fields": list(self.changed_fields), "invalidated_evidence_count": self.invalidated_evidence_count}


def understand_turn(question: str, *, action: str, previous: TaskState | None) -> TaskDelta:
    """本地、确定性、保守地解析 B1；歧义时产出 clarification，不调用模型或网络。"""

    text = " ".join(question.split())
    # 支持“2026 年 7 月和 8 月”：后一个月份继承同一句中最近的显式年份。
    parsed_periods: list[str] = []
    current_year: str | None = None
    for year, month in re.findall(r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月", text):
        current_year = year or current_year
        if current_year is not None:
            parsed_periods.append(f"{current_year}-{int(month):02d}")
    periods = tuple(dict.fromkeys(parsed_periods))
    metric = next(
        (key for key, aliases in _B1_VOCABULARY["metric_aliases"].items() if any(token in text for token in aliases)),
        None,
    )
    if metric is None and "净退款" in text:
        metric = "net_refund_amount"
    previous_constraints = dict(previous.constraints) if previous else {}
    # “改成 8 月，并和 7 月比较”里的年份来自已确认 task，而不是当前 turn 自行猜测。
    previous_periods = tuple(previous_constraints.get("periods", ()))
    if previous_periods:
        context_year = str(previous_periods[-1]).split("-", 1)[0]
        relative_periods = tuple(
            f"{context_year}-{int(month):02d}"
            for month in re.findall(r"(?<!\d)(\d{1,2})\s*月", text)
        )
        periods = tuple(dict.fromkeys((*periods, *relative_periods)))
    # lifecycle action 由严格 task envelope 决定；自由文本不能把 continue 偷换成 cancel/switch。
    if action == "cancel":
        return TaskDelta(category="cancel", route="none")
    category: DeltaCategory = {"start": "start_task", "continue": "continue", "switch": "switch_task"}.get(action, "continue")  # type: ignore[assignment]
    policy_intent = any(token in text for token in ("退款规则", "退款政策", "全额退款", "前提和材料", "客服处理"))
    channel_intent = any(token in text for token in ("按渠道", "渠道维度", "各渠道"))
    product_intent = any(token in text for token in ("哪些商品", "商品最突出", "按商品", "商品维度"))
    reason_intent = any(token in text for token in ("退款原因", "按原因", "质量问题", "为什么"))
    if any(token in text for token in _B1_VOCABULARY["correction_aliases"]):
        category = "correct_previous_understanding"
    elif channel_intent and previous is not None:
        category = "modify_constraint"
    elif policy_intent:
        category = "add_evidence_requirement"
    elif action == "continue" and ("改成" in text or "调整" in text):
        category = "modify_constraint"
    elif action == "continue" and any(token in text for token in ("为什么", "解释这个结果")):
        category = "ask_about_existing_result"
    elif action == "continue" and any(token in text for token in ("再查证", "补充证据")):
        category = "add_evidence_requirement"
    resolved_metric = metric or previous_constraints.get("metric")
    resolved_periods = periods
    if category in {"modify_constraint", "correct_previous_understanding"} and periods and any(token in text for token in ("相比", "比较", "对比", "和")):
        old_periods = previous_periods
        resolved_periods = tuple(dict.fromkeys((*old_periods, *periods)))
    elif not periods and category in {"continue", "ask_about_existing_result", "add_evidence_requirement"}:
        resolved_periods = tuple(previous_constraints.get("periods", ()))
    pending: list[str] = []
    if category not in {"cancel", "ask_about_existing_result"}:
        if not resolved_metric:
            pending.append("metric")
        if not resolved_periods:
            pending.append("periods")
    constraints: list[tuple[str, Any]] = []
    if resolved_metric:
        constraints.append(("metric", resolved_metric))
    if resolved_periods:
        constraints.append(("periods", resolved_periods))
    if len(resolved_periods) > 1:
        constraints.append(("comparison", True))
    if channel_intent:
        constraints.append(("breakdown_dimension", "channel"))
    elif product_intent:
        constraints.append(("breakdown_dimension", "product"))
    elif reason_intent:
        constraints.append(("breakdown_dimension", "reason"))

    period_key = ",".join(resolved_periods)
    period_label = "、".join(
        f"{year} 年 {int(month)} 月" for year, month in (period.split("-", 1) for period in resolved_periods)
    )
    typed: list[EvidenceRequirement] = []
    if not pending and resolved_metric and resolved_periods:
        if product_intent:
            typed.extend((
                EvidenceRequirement(
                    f"sql:refund_reason:quality_issue:{period_key}", "sql", "quality_driver",
                    f"查询 {period_label} 按退款原因拆分实际净退款金额，保留负数冲销并计算各原因增量。",
                ),
                EvidenceRequirement(
                    f"sql:product_sku:quality_issue:{period_key}", "sql", "quality_product_breakdown",
                    f"查询 {period_label} 质量问题退款按商品 SKU 的实际净退款金额和增量，并与总额对账。",
                    depends_on="quality_increment_positive",
                ),
            ))
        elif channel_intent:
            typed.append(EvidenceRequirement(
                f"sql:channel:{period_key}", "sql", "channel_breakdown",
                f"查询 {period_label} 按渠道拆分实际净退款金额和增量，保留负数冲销并与总额对账。",
            ))
        elif reason_intent:
            typed.append(EvidenceRequirement(
                f"sql:refund_reason:{period_key}", "sql", "reason_breakdown",
                f"查询 {period_label} 按退款原因拆分实际净退款金额，保留负数冲销并计算各原因增量。",
            ))
        else:
            typed.append(EvidenceRequirement(
                f"sql:{resolved_metric}:{period_key}", "sql", "metric_comparison",
                f"查询 {period_label} 的实际净退款金额，并计算差额和变化率。" if len(resolved_periods) > 1
                else f"查询 {period_label} 的实际净退款金额。",
            ))
    if policy_intent and not pending:
        # ★ Hybrid 必须拥有本轮 SQL Evidence，不能拿 TaskState 中只有引用、没有 rows 的旧结果
        # 冒充可供 Synthesizer 消费的当前上下文。
        if not typed:
            typed.append(EvidenceRequirement(
                f"sql:quality_refund_change:{period_key}", "sql", "quality_driver",
                f"查询 {period_label} 质量问题实际净退款金额和增量，保留负数冲销并与总额对账。",
            ))
        typed.append(EvidenceRequirement(
            "document:refund_policy_basic+refund_policy_quality", "document", "refund_policy_interpretation",
            text, runtime_scope="business_release",
            expected_document_keys=("refund_policy_basic", "refund_policy_quality"),
        ))
    requirements = tuple(item.identity for item in typed)
    goal = "查询实际净退款金额" if resolved_metric else None
    route = "none" if pending else ("hybrid" if policy_intent else "sql")
    return TaskDelta(
        category=category, goal=goal, set_constraints=tuple(constraints), add_requirements=requirements,
        evidence_requirements=tuple(typed), route=route, pending_questions=tuple(pending),
    )


def apply_delta(previous: TaskState | None, delta: TaskDelta, *, owner_ref: str) -> tuple[TaskState, TaskTransition]:
    """原子地合并 delta，并在执行语义改变时使旧证据失效。"""

    before = previous.identity if previous else None
    source = previous or TaskState(owner_ref=owner_ref)
    if source.owner_ref != owner_ref:
        raise ValueError("task_owner_mismatch")
    # switch 创建独立新任务：旧约束、requirement、Evidence 和 generation 都不能串入新 task。
    base = TaskState(owner_ref=owner_ref) if delta.category == "switch_task" else source
    constraints = dict(base.constraints)
    for key in delta.remove_constraints:
        constraints.pop(key, None)
    constraints.update(dict(delta.set_constraints))
    changed = []
    old_projection = base.safe_projection()
    status: TaskStatus = "active"
    termination = None
    if delta.category == "cancel":
        status, termination = "cancelled", "cancelled_by_caller"
    elif delta.category == "switch_task":
        status = "active"
    elif delta.pending_questions:
        status = "clarification_required"
    if delta.category in {"start_task", "modify_constraint", "correct_previous_understanding", "switch_task"}:
        requirements = delta.add_requirements
        evidence_requirements = delta.evidence_requirements
    else:
        requirements = tuple(dict.fromkeys((*base.requirements, *delta.add_requirements)))
        indexed = {item.identity: item for item in (*base.evidence_requirements, *delta.evidence_requirements)}
        evidence_requirements = tuple(indexed[item] for item in requirements if item in indexed)
    semantic_change = bool(
        previous
        and (
            delta.category == "cancel"
            or (
                delta.category in {"modify_constraint", "correct_previous_understanding"}
                and (dict(delta.set_constraints) or delta.route != base.route)
            )
        )
    )
    invalidation_reason = "task_cancelled" if delta.category == "cancel" else "task_semantics_changed"
    invalidated = tuple(replace(item, validity="invalidated", invalidation_reason=invalidation_reason) if semantic_change and item.validity == "active" else item for item in base.evidence)
    generation = 1 if delta.category == "switch_task" else base.generation + (1 if previous else 0)
    state = TaskState(
        owner_ref=owner_ref, generation=generation, status=status, goal=delta.goal or base.goal,
        constraints=tuple(sorted(constraints.items())), pending_questions=delta.pending_questions,
        requirements=requirements, evidence_requirements=evidence_requirements,
        route=delta.route or base.route, evidence=invalidated, termination=termination,
    )
    for key, value in state.safe_projection().items():
        if old_projection.get(key) != value:
            changed.append(key)
    invalidated_count = sum(1 for old, new in zip(base.evidence, invalidated) if old.validity != new.validity)
    if delta.category == "switch_task" and previous:
        invalidated_count = sum(1 for item in previous.evidence if item.validity == "active")
    transition = TaskTransition(delta.category, before, state.identity, tuple(changed), invalidated_count)
    return state, transition


def attach_evidence(
    state: TaskState,
    refs: tuple[Mapping[str, Any], ...],
    *,
    requirement_identity: str | None = None,
    action_id: str | None = None,
    input_fingerprint: str | None = None,
    runtime_identity: str | None = None,
) -> TaskState:
    """把本轮 Harness 的安全 EvidenceRef 接入任务，不接入 rows/doc body/answer。"""

    requirement = requirement_identity or (state.requirements[-1] if state.requirements else "unspecified")
    additions = tuple(
        TaskEvidence(
            dict(ref), "document" if ref.get("evidence_kind") == "document" else "sql", requirement,
            source_generation=state.generation, action_id=action_id, input_fingerprint=input_fingerprint,
            runtime_identity=runtime_identity,
        )
        for ref in refs
    )
    return replace(state, evidence=(*state.evidence, *additions))


@dataclass(frozen=True)
class NodeContext:
    """一个节点实际收到的白名单上下文及其可复核 fingerprint。"""

    purpose: str
    source_identities: tuple[str, ...]
    payload: Mapping[str, Any]
    field_budget: int
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        if len(self.payload) > self.field_budget:
            raise ValueError("node_context_budget_exceeded")
        object.__setattr__(self, "identity", canonical_hash({"purpose": self.purpose, "source_identities": self.source_identities, "payload": self.payload}))

    def safe_projection(self) -> dict[str, Any]:
        return {"purpose": self.purpose, "source_identities": list(self.source_identities), "payload": dict(self.payload), "field_budget": self.field_budget, "input_fingerprint": self.identity}


def project_node_contexts(
    *, question: str, state: TaskState, delta: TaskDelta, prior_state_identity: str | None = None
) -> tuple[NodeContext, ...]:
    """按节点目的投影实际输入；禁止携带历史答案、rows 或文档正文。"""

    state_id = state.identity
    return (
        NodeContext("turn_understanding", (delta.source_identity,), {"question": question, "prior_state_identity": prior_state_identity}, 2),
        NodeContext("route_execution", (state_id,), {"goal": state.goal, "constraints": dict(state.constraints), "requirements": list(state.requirements), "route": state.route}, 4),
        NodeContext("sql", (state_id,), {"metric": dict(state.constraints).get("metric"), "periods": list(dict(state.constraints).get("periods", ())), "requirement": state.requirements[-1] if state.requirements else None}, 3),
        NodeContext("controller_response", (state_id,), {"status": state.status, "route": state.route, "pending_questions": list(state.pending_questions), "active_evidence_refs": [item.ref for item in state.evidence if item.validity == "active"]}, 4),
    )
