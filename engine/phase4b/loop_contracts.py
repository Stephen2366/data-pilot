"""M44-B：顶层 Decision Loop 的 typed 事实与纯预算状态机。

★ Controller 只认识本模块的 interface，不解析 SQL/RAG 深 Tool 的私有对象。这样预算、
EvidenceDelta、Progress 和停止语义集中在一处，API/Trace/Eval 也能从同一事实投影。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from engine.phase4b.identity import canonical_hash

RequirementKind = Literal["sql", "document"]
ActionId = Literal[
    "collect_sql_evidence", "repair_sql_evidence", "collect_document_evidence", "clarify", "stop"
]
TerminationReason = Literal[
    "answer_ready", "clarification_required", "no_progress", "budget_exhausted", "unsafe",
    "external_unavailable", "unrecoverable", "agent_loop_contract_failure",
]


@dataclass(frozen=True)
class EvidenceRequirement:
    """服务端生成的 Evidence 缺口；请求体不能构造或覆盖。"""

    identity: str
    kind: RequirementKind
    purpose: str
    query: str
    runtime_scope: Literal["business_release", "external_profile", "not_applicable"] = "not_applicable"
    expected_document_keys: tuple[str, ...] = ()
    depends_on: str | None = None
    required: bool = True
    freshness: Literal["current_run", "task_state"] = "current_run"

    def __post_init__(self) -> None:
        if not self.identity.strip() or not self.purpose.strip() or not self.query.strip():
            raise ValueError("evidence_requirement_invalid")
        if self.kind == "sql" and self.runtime_scope != "not_applicable":
            raise ValueError("sql_requirement_runtime_invalid")
        if self.kind == "document" and self.runtime_scope == "not_applicable":
            raise ValueError("document_requirement_runtime_missing")
        if self.kind == "sql" and self.expected_document_keys:
            raise ValueError("sql_requirement_document_keys_invalid")

    def safe_projection(self) -> dict[str, Any]:
        return {
            "identity": self.identity, "kind": self.kind, "purpose": self.purpose,
            "runtime_scope": self.runtime_scope, "expected_document_keys": list(self.expected_document_keys),
            "depends_on": self.depends_on, "required": self.required, "freshness": self.freshness,
            "query_fingerprint": canonical_hash(self.query),
        }


@dataclass(frozen=True)
class BudgetProfile:
    """G44-3 方案 A 的 hard limits；identity 参与 Trace/Eval 对账。"""

    identity: str
    max_actions: int = 3
    max_deep_tools: int = 3
    max_sql_actions: int = 3
    max_knowledge_actions: int = 1
    max_repairs_per_requirement: int = 1
    max_retrieval_batches: int = 1
    max_candidates: int = 5
    max_selected: int = 3
    max_generation_visible: int = 3
    max_model_calls: int = 6
    max_total_tokens: int = 24000

    def safe_projection(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ResourceConsumption:
    """一次 Action 的实际资源消费；token 未观测时绝不伪造为已观测。"""

    actions: int = 0
    deep_tools: int = 0
    sql_actions: int = 0
    knowledge_actions: int = 0
    repairs: int = 0
    retrieval_batches: int = 0
    candidates: int = 0
    selected: int = 0
    generation_visible: int = 0
    model_calls: int = 0
    total_tokens: int = 0
    token_usage_observed: bool = False
    timeouts: int = 0
    latency_ms: float = 0.0

    def __post_init__(self) -> None:
        numeric = (
            self.actions, self.deep_tools, self.sql_actions, self.knowledge_actions, self.repairs,
            self.retrieval_batches, self.candidates, self.selected, self.generation_visible,
            self.model_calls, self.total_tokens, self.timeouts,
        )
        if any(value < 0 for value in numeric) or self.latency_ms < 0:
            raise ValueError("resource_consumption_negative")
        # token_usage_observed=False 时 total_tokens 只能解释为“已知部分和”，不能用来宣称
        # 完整成本或触发精确 token Gate；调用次数硬门仍照常生效。

    def add(self, other: "ResourceConsumption") -> "ResourceConsumption":
        """逐维累加，布尔位只有两侧都已观察才可声称完整。"""

        return ResourceConsumption(
            actions=self.actions + other.actions,
            deep_tools=self.deep_tools + other.deep_tools,
            sql_actions=self.sql_actions + other.sql_actions,
            knowledge_actions=self.knowledge_actions + other.knowledge_actions,
            repairs=self.repairs + other.repairs,
            retrieval_batches=self.retrieval_batches + other.retrieval_batches,
            candidates=self.candidates + other.candidates,
            selected=self.selected + other.selected,
            generation_visible=self.generation_visible + other.generation_visible,
            model_calls=self.model_calls + other.model_calls,
            total_tokens=self.total_tokens + other.total_tokens,
            token_usage_observed=self.token_usage_observed and other.token_usage_observed,
            timeouts=self.timeouts + other.timeouts,
            latency_ms=round(self.latency_ms + other.latency_ms, 3),
        )

    def safe_projection(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class BudgetLedger:
    """先检查、后消费的不可变父账本。"""

    profile: BudgetProfile
    consumed: ResourceConsumption = field(default_factory=lambda: ResourceConsumption(token_usage_observed=True))

    def allows(self, declared: ResourceConsumption, *, repair_count_for_requirement: int = 0) -> bool:
        """在网络/DB 调用前逐维检查预算；repair 次数按当前 requirement 单独传入。"""

        projected = self.consumed.add(declared)
        return all((
            projected.actions <= self.profile.max_actions,
            projected.deep_tools <= self.profile.max_deep_tools,
            projected.sql_actions <= self.profile.max_sql_actions,
            projected.knowledge_actions <= self.profile.max_knowledge_actions,
            repair_count_for_requirement + declared.repairs <= self.profile.max_repairs_per_requirement,
            projected.retrieval_batches <= self.profile.max_retrieval_batches,
            projected.candidates <= self.profile.max_candidates,
            projected.selected <= self.profile.max_selected,
            projected.generation_visible <= self.profile.max_generation_visible,
            projected.model_calls <= self.profile.max_model_calls,
            not projected.token_usage_observed or projected.total_tokens <= self.profile.max_total_tokens,
        ))

    def consume(self, actual: ResourceConsumption) -> "BudgetLedger":
        """消费后再次校验；深 Tool 超出声明上限时合同失败而非负账。"""

        if not self.allows(actual):
            raise ValueError("budget_consumption_exceeded")
        return BudgetLedger(self.profile, self.consumed.add(actual))

    def safe_projection(self) -> dict[str, Any]:
        return {"profile": self.profile.safe_projection(), "consumed": self.consumed.safe_projection()}


@dataclass(frozen=True)
class EvidenceDelta:
    """动作前后 Evidence identity 的集合差分，不读取答案文案。"""

    added: tuple[Mapping[str, Any], ...] = ()
    removed: tuple[str, ...] = ()
    invalidated: tuple[str, ...] = ()
    duplicate: tuple[str, ...] = ()

    @property
    def gained(self) -> bool:
        """只有新增 EvidenceRef 才算进展；answer 文案变化不算。"""

        return bool(self.added)

    def safe_projection(self) -> dict[str, Any]:
        return {
            "added": [dict(item) for item in self.added], "removed": list(self.removed),
            "invalidated": list(self.invalidated), "duplicate": list(self.duplicate),
        }


@dataclass(frozen=True)
class AgentNodeContext:
    """M44 actual-node Context v2：显式 allowlist、字段预算与近似 token 预算。"""

    purpose: str
    source_identities: tuple[str, ...]
    payload: Mapping[str, Any]
    allowed_fields: tuple[str, ...]
    field_budget: int
    token_budget: int
    context_version: str = "phase4b-agent-node-context-v2"
    # M48：v3 Context 可以携带仅供节点消费的短期字段；safe_projection 只投影 hash。
    private_fields: tuple[str, ...] = ()
    identity: str = field(init=False)
    estimated_tokens: int = field(init=False)

    def __post_init__(self) -> None:
        if set(self.payload) - set(self.allowed_fields) or len(self.payload) > self.field_budget:
            raise ValueError("agent_node_context_fields_invalid")
        if set(self.private_fields) - set(self.payload):
            raise ValueError("agent_node_context_private_fields_invalid")
        if self.private_fields and self.context_version != "phase4b-agent-node-context-v3":
            raise ValueError("agent_node_context_private_version_invalid")
        estimated = max(1, (len(str(dict(self.payload))) + 3) // 4)
        if estimated > self.token_budget:
            raise ValueError("agent_node_context_token_budget_exceeded")
        object.__setattr__(self, "estimated_tokens", estimated)
        identity_payload = {
            "context_version": self.context_version, "purpose": self.purpose,
            "source_identities": self.source_identities, "payload": self.payload,
            "allowed_fields": self.allowed_fields, "field_budget": self.field_budget,
            "token_budget": self.token_budget,
        }
        # v2 identity 必须逐字兼容；只有 additive v3 才把 private allowlist 绑定进 hash。
        if self.private_fields:
            identity_payload["private_fields"] = self.private_fields
        object.__setattr__(self, "identity", canonical_hash(identity_payload))

    def safe_projection(self) -> dict[str, Any]:
        public_payload = {
            key: (
                {"redacted": True, "value_identity": canonical_hash(value),
                 "item_count": len(value) if isinstance(value, (list, tuple)) else None}
                if key in self.private_fields else value
            )
            for key, value in self.payload.items()
        }
        result = {
            "context_version": self.context_version, "purpose": self.purpose,
            "source_identities": list(self.source_identities), "payload": public_payload,
            "allowed_fields": list(self.allowed_fields), "field_budget": self.field_budget,
            "token_budget": self.token_budget, "estimated_tokens": self.estimated_tokens,
            "input_fingerprint": self.identity,
        }
        if self.private_fields:
            result["private_fields"] = list(self.private_fields)
        return result


@dataclass(frozen=True)
class ProgressDecision:
    """只回答 coverage 是否增加以及是否还存在合法动作；它不是 Answer Gate。"""

    coverage_increased: bool
    eligible_action_remains: bool
    reason_code: str

    def safe_projection(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ActionAttempt:
    """一项顶层 Evidence Action 的完整安全账本。"""

    ordinal: int
    action_id: ActionId
    requirement_identity: str
    input_fingerprint: str
    duplicate_key: str
    status: Literal["completed", "blocked", "failed", "external_unavailable"]
    observation: Mapping[str, Any]
    budget_before: Mapping[str, Any]
    consumed: ResourceConsumption
    budget_after: Mapping[str, Any]
    evidence_delta: EvidenceDelta
    progress: ProgressDecision

    def safe_projection(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal, "action_id": self.action_id,
            "requirement_identity": self.requirement_identity, "input_fingerprint": self.input_fingerprint,
            "duplicate_key": self.duplicate_key, "status": self.status, "observation": dict(self.observation),
            "budget_before": dict(self.budget_before), "consumed": self.consumed.safe_projection(),
            "budget_after": dict(self.budget_after), "evidence_delta": self.evidence_delta.safe_projection(),
            "progress": self.progress.safe_projection(),
        }


@dataclass(frozen=True)
class TerminationFact:
    """唯一稳定停止事实；框架异常和业务预算不会混为一类。"""

    reason: TerminationReason
    detail_code: str
    active_requirement_identities: tuple[str, ...]
    unresolved_requirement_identities: tuple[str, ...]

    def safe_projection(self) -> dict[str, Any]:
        return {
            "reason": self.reason, "detail_code": self.detail_code,
            "active_requirement_identities": list(self.active_requirement_identities),
            "unresolved_requirement_identities": list(self.unresolved_requirement_identities),
        }
