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

DeltaCategory = Literal["start_task", "continue", "modify_constraint", "ask_about_existing_result", "add_evidence_requirement", "switch_task", "correct_previous_understanding", "cancel"]
TaskStatus = Literal["active", "clarification_required", "cancelled", "switched", "cleared"]

TASK_STATE_VERSION = "phase4b-task-state-v1"
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
        return {"category": self.category, "goal": self.goal, "set_constraints": dict(self.set_constraints), "remove_constraints": list(self.remove_constraints), "add_requirements": list(self.add_requirements), "route": self.route, "pending_questions": list(self.pending_questions), "source_identity": self.source_identity}


@dataclass(frozen=True)
class TaskEvidence:
    """只保存可审计引用和 validity，不长期保存 rows、正文或答案。"""

    ref: Mapping[str, Any]
    route: str
    requirement_identity: str
    validity: Literal["active", "invalidated"] = "active"
    invalidation_reason: str | None = None
    source_generation: int = 1

    def safe_projection(self) -> dict[str, Any]:
        return {"ref": dict(self.ref), "route": self.route, "requirement_identity": self.requirement_identity, "validity": self.validity, "invalidation_reason": self.invalidation_reason, "source_generation": self.source_generation}


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
    route: Literal["sql", "rag", "hybrid", "none"] = "none"
    evidence: tuple[TaskEvidence, ...] = ()
    termination: str | None = None
    state_version: str = TASK_STATE_VERSION

    @property
    def identity(self) -> str:
        return canonical_hash(self.safe_projection())

    def safe_projection(self) -> dict[str, Any]:
        return {"state_version": self.state_version, "generation": self.generation, "status": self.status, "goal": self.goal, "constraints": dict(self.constraints), "pending_questions": list(self.pending_questions), "requirements": list(self.requirements), "route": self.route, "evidence": [item.safe_projection() for item in self.evidence], "termination": self.termination}


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
    periods = tuple(dict.fromkeys(f"{year}-{int(month):02d}" for year, month in re.findall(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", text)))
    metric = next(
        (key for key, aliases in _B1_VOCABULARY["metric_aliases"].items() if any(token in text for token in aliases)),
        None,
    )
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
    if any(token in text for token in _B1_VOCABULARY["correction_aliases"]):
        category = "correct_previous_understanding"
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
    requirements = (f"sql:{resolved_metric}:{','.join(resolved_periods)}",) if resolved_metric and resolved_periods else ()
    goal = "查询实际净退款金额" if resolved_metric else None
    return TaskDelta(category=category, goal=goal, set_constraints=tuple(constraints), add_requirements=requirements, route="none" if pending else "sql", pending_questions=tuple(pending))


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
    else:
        requirements = tuple(dict.fromkeys((*base.requirements, *delta.add_requirements)))
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
    state = TaskState(owner_ref=owner_ref, generation=generation, status=status, goal=delta.goal or base.goal, constraints=tuple(sorted(constraints.items())), pending_questions=delta.pending_questions, requirements=requirements, route=delta.route or base.route, evidence=invalidated, termination=termination)
    for key, value in state.safe_projection().items():
        if old_projection.get(key) != value:
            changed.append(key)
    invalidated_count = sum(1 for old, new in zip(base.evidence, invalidated) if old.validity != new.validity)
    if delta.category == "switch_task" and previous:
        invalidated_count = sum(1 for item in previous.evidence if item.validity == "active")
    transition = TaskTransition(delta.category, before, state.identity, tuple(changed), invalidated_count)
    return state, transition


def attach_evidence(state: TaskState, refs: tuple[Mapping[str, Any], ...]) -> TaskState:
    """把本轮 Harness 的安全 EvidenceRef 接入任务，不接入 rows/doc body/answer。"""

    requirement = state.requirements[-1] if state.requirements else "unspecified"
    additions = tuple(TaskEvidence(dict(ref), state.route, requirement, source_generation=state.generation) for ref in refs)
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
