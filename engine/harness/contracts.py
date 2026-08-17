"""M35–M37 Harness 的最小跨节点/turn 合同。

★ 这些 dataclass 是 Graph state 中可审计的“事实卡片”，而不是把 SQL/RAG 内部对象塞进顶层
State 的万能袋。调用者只需要认识请求、route 决定、Tool Observation 和最终结果四种对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.schemas.agent import ToolCallTrace
from engine.governance import TrustedCaller
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import EvidenceRef
from engine.trace.recorder import TraceStep

Route = Literal["sql", "rag", "none"]
ExecutionStatus = Literal["not_started", "completed", "external_unavailable", "failed"]
AnswerStatus = Literal[
    "complete", "partial", "clarification_required", "unsupported", "insufficient_evidence", "no_answer"
]
SafetyStatus = Literal["passed", "blocked"]
TerminationAction = Literal["answer", "clarify", "unsupported", "blocked", "failed"]
ClarificationValueType = Literal["text", "time_range", "enum"]
KnowledgeRuntimeKind = Literal["business_release", "external_profile", "not_applicable"]


class HarnessContractError(ValueError):
    """Harness 收到不闭合的 route/observation 时抛出的合同错误。"""


@dataclass(frozen=True)
class ClarificationFieldSpec:
    """一次澄清中允许用户补充的单个 typed 字段。

    ★ M36 不把任意聊天文本直接拼回 Prompt，而是先要求 caller 按闭集字段补条件。这样既能
    精确检查“缺了什么”，也能阻止额外 key 偷渡成新的系统指令或检索动作。
    """

    key: str
    label: str
    value_type: ClarificationValueType
    allowed_values: tuple[str, ...] = ()
    max_length: int = 80

    def __post_init__(self) -> None:
        """在字段说明进入 Router/checkpoint 前执行 closed-world 校验。"""

        if self.value_type not in {"text", "time_range", "enum"}:
            raise HarnessContractError("未知 clarification value_type")
        if not self.key.strip() or not self.label.strip() or self.max_length <= 0:
            raise HarnessContractError("clarification field 必须有 key/label 和正数 max_length")
        if self.value_type == "enum" and not self.allowed_values:
            raise HarnessContractError("enum clarification field 必须声明 allowed_values")
        if self.value_type != "enum" and self.allowed_values:
            raise HarnessContractError("只有 enum clarification field 可以声明 allowed_values")

    def safe_projection(self) -> dict[str, Any]:
        """返回可公开的字段说明，不包含任何用户已经填写的值。"""

        return {
            "key": self.key,
            "label": self.label,
            "value_type": self.value_type,
            "allowed_values": list(self.allowed_values),
            "max_length": self.max_length,
        }


@dataclass(frozen=True)
class ClarificationSpec:
    """Router 为 pending clarification 生成的 closed-world 恢复说明。"""

    identity: str
    prompt: str
    fields: tuple[ClarificationFieldSpec, ...]
    context_template: Literal["subject", "analytics_scope"]

    def __post_init__(self) -> None:
        """拒绝重复字段和未知 Context 模板，避免恢复层临时猜测。"""

        if self.context_template not in {"subject", "analytics_scope"}:
            raise HarnessContractError("未知 clarification context_template")
        if not self.identity.strip() or not self.prompt.strip() or not self.fields:
            raise HarnessContractError("clarification spec 必须有 identity/prompt/fields")
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise HarnessContractError("clarification spec field key 不能重复")

    def safe_projection(self) -> dict[str, Any]:
        """公开待补问题与字段合同；context template 属内部控制信息，不向客户端暴露。"""

        return {
            "identity": self.identity,
            "prompt": self.prompt,
            "fields": [field.safe_projection() for field in self.fields],
        }


@dataclass(frozen=True)
class FollowUpActionSpec:
    """成功回答后由服务端签发的一种 closed-world 追问动作。"""

    action: Literal["adjust_sql_scope", "explain_same_evidence", "ask_related_evidence"]
    label: str
    fields: tuple[ClarificationFieldSpec, ...]
    requirement_equivalent: bool

    def __post_init__(self) -> None:
        """动作与等价性由代码冻结，客户端不能自行声明 Evidence 可复用。"""

        if not self.label.strip() or len({field.key for field in self.fields}) != len(self.fields):
            raise HarnessContractError("follow-up action spec 非法")
        if self.action == "explain_same_evidence" and not self.requirement_equivalent:
            raise HarnessContractError("同 Evidence 解释动作必须声明 requirement 等价")
        if self.action != "explain_same_evidence" and self.requirement_equivalent:
            raise HarnessContractError("只有同 Evidence 解释动作可以声明 requirement 等价")

    def safe_projection(self) -> dict[str, Any]:
        """公开动作和字段说明，不公开旧任务值或 Evidence identity。"""

        return {
            "action": self.action,
            "label": self.label,
            "fields": [field.safe_projection() for field in self.fields],
        }


@dataclass(frozen=True)
class FollowUpSpec:
    """一个成功 SQL/RAG 结果允许消费的一次追问动作集合。"""

    identity: str
    actions: tuple[FollowUpActionSpec, ...]

    def __post_init__(self) -> None:
        """拒绝空集合和重复 action，避免 API 临时发明行为。"""

        action_names = [item.action for item in self.actions]
        if not self.identity.strip() or not action_names or len(action_names) != len(set(action_names)):
            raise HarnessContractError("follow-up spec 必须非空且 action 唯一")

    def safe_projection(self) -> dict[str, Any]:
        """返回客户端可据以渲染表单的安全视图。"""

        return {"identity": self.identity, "actions": [item.safe_projection() for item in self.actions]}


@dataclass(frozen=True)
class FollowUpExecutionContext:
    """仅交给本轮深 Tool 的旧证据审计坐标，不包含旧答案、rows 或正文。"""

    action: str
    previous_route: Literal["sql", "rag"]
    requirement_equivalent: bool
    previous_requirement: AnswerEvidenceRequirement | None
    current_requirement: AnswerEvidenceRequirement | None
    old_evidence_refs: tuple[EvidenceRef, ...]
    knowledge_runtime_kind: KnowledgeRuntimeKind

    def __post_init__(self) -> None:
        """禁止跨 route/跨 runtime 伪造可复用上下文。"""

        if not self.action.strip() or not self.old_evidence_refs:
            raise HarnessContractError("follow-up execution context 缺少 action/EvidenceRef")
        expected_kind = "sql" if self.previous_route == "sql" else "document"
        if any(ref.evidence_kind != expected_kind for ref in self.old_evidence_refs):
            raise HarnessContractError("follow-up route 与旧 Evidence kind 不一致")
        if self.previous_route == "sql" and self.knowledge_runtime_kind != "not_applicable":
            raise HarnessContractError("SQL follow-up 不得声明 knowledge runtime")
        if self.previous_route == "rag" and self.previous_requirement is None:
            raise HarnessContractError("RAG follow-up 必须携带服务端旧 requirement")
        if self.previous_route == "rag" and self.current_requirement is None:
            raise HarnessContractError("RAG follow-up 必须形成服务端新 requirement")
        if self.previous_route == "rag" and self.previous_requirement and self.current_requirement:
            identities_equal = self.previous_requirement.identity == self.current_requirement.identity
            if identities_equal != self.requirement_equivalent:
                raise HarnessContractError("follow-up requirement identity 与等价声明不一致")
        if self.previous_route == "sql" and (self.previous_requirement is not None or self.current_requirement is not None):
            raise HarnessContractError("SQL follow-up 不得携带 RAG requirement")


@dataclass(frozen=True)
class HarnessRequest:
    """一次单轮运行的安全输入。

    ``caller`` 允许为空，是为了让无 resolver/role 篡改也能经过同一个顶层 Harness 形成
    `caller_untrusted` 终止事实；它绝不会被 Tool 当成可授权 caller 使用。
    """

    question: str
    run_id: str
    caller: TrustedCaller | None
    active_sql_role: str | None
    force_new_pipeline: bool = True
    schema_retrieval_profile: str = "default"
    schema_fusion_strategy: str = "weighted"
    enable_bounded_follow_up: bool = False
    follow_up_context: FollowUpExecutionContext | None = None

    def __post_init__(self) -> None:
        """保证 Graph identity 与当前问题非空。"""

        if not self.question.strip() or not self.run_id.strip():
            raise HarnessContractError("question 和 run_id 不能为空")


@dataclass(frozen=True)
class RouteDecision:
    """Router 的封闭决定；它不能携带 Tool 输出、文档正文或答案。"""

    route: Route
    reason_code: str
    needs_evidence: bool
    termination_action: TerminationAction
    decision_source: Literal["deterministic", "controller"] = "deterministic"
    requirement: AnswerEvidenceRequirement | None = None
    clarification_spec: ClarificationSpec | None = None

    def __post_init__(self) -> None:
        """校验 route、Evidence requirement 与终止动作组成闭合决定。"""

        if self.route == "none" and self.needs_evidence:
            raise HarnessContractError("none route 不能请求 Evidence")
        if self.route != "none" and not self.needs_evidence:
            raise HarnessContractError("SQL/RAG route 必须请求 Evidence")
        if self.route == "rag" and self.requirement is None:
            raise HarnessContractError("RAG route 必须带受控 requirement")
        if self.route != "rag" and self.requirement is not None:
            raise HarnessContractError("只有 RAG route 可以携带 requirement")
        if self.termination_action == "clarify" and self.clarification_spec is None:
            raise HarnessContractError("clarify 决定必须携带 closed-world clarification spec")
        if self.termination_action != "clarify" and self.clarification_spec is not None:
            raise HarnessContractError("只有 clarify 决定可以携带 clarification spec")


@dataclass(frozen=True)
class ToolObservation:
    """深 Tool 向顶层报告的安全事实。

    SQL rows 仍是历史 API 兼容投影所需的已 Guard 结果；Document Evidence 正文不会离开
    AnswerFlow，顶层只保存已校验 citation、ledger 和 EvidenceRef 的安全投影。
    """

    tool_name: Literal["text2sql", "rag_answer_flow"]
    route: Literal["sql", "rag"]
    execution_status: ExecutionStatus
    answer_status: AnswerStatus
    safety_status: SafetyStatus
    reason_code: str
    answer: str | None = None
    sql: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, Any], ...] = ()
    tables_used: tuple[str, ...] = ()
    chart_spec: dict[str, Any] | None = None
    citations: tuple[dict[str, Any], ...] = ()
    docs_used: tuple[dict[str, Any], ...] = ()
    tool_calls: tuple[ToolCallTrace, ...] = ()
    trace_steps: tuple[TraceStep, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    ledger_projection: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    blocked_reason: str | None = None
    error_type: str | None = None
    sql_time_ms: float = 0.0
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None
    langfuse_write_status: str = "skipped"
    langfuse_span_mode: str = "post_hoc"

    def __post_init__(self) -> None:
        """防止 Tool 类型、route 与安全状态在投影时互相矛盾。"""

        if self.route == "sql" and self.tool_name != "text2sql":
            raise HarnessContractError("SQL Observation 必须来自 text2sql Tool")
        if self.route == "rag" and self.tool_name != "rag_answer_flow":
            raise HarnessContractError("RAG Observation 必须来自 RAGAnswerFlow")
        if self.safety_status == "blocked" and not self.blocked_reason:
            raise HarnessContractError("安全拦截必须携带可公开的 blocked_reason")
        if self.safety_status == "passed" and self.blocked_reason is not None:
            raise HarnessContractError("技术失败不能借用 blocked_reason")


@dataclass(frozen=True)
class AgentRunResult:
    """Harness 的唯一出站事实，API/Trace/Eval 都只能从它做单向投影。"""

    route: Route
    execution_status: ExecutionStatus
    answer_status: AnswerStatus
    safety_status: SafetyStatus
    reason_code: str
    answer: str
    route_decision: RouteDecision
    observation: ToolObservation | None
    termination_action: TerminationAction
    graph_steps: tuple[str, ...]
    caller_safe_ref: str | None

    def __post_init__(self) -> None:
        """确保最终四轴、Router 决定与 Observation 都来自同一路径。"""

        if self.route != self.route_decision.route:
            raise HarnessContractError("最终 route 必须与 RouteDecision 一致")
        if self.observation is not None and self.observation.route != self.route:
            raise HarnessContractError("Observation route 与最终 route 不一致")
        if self.observation is None and self.route != "none":
            raise HarnessContractError("需要 Tool 的 route 不能缺 Observation")
        if self.safety_status == "blocked" and not self.answer:
            raise HarnessContractError("blocked 结果仍必须有安全的用户文案")
