"""M35 Harness 的最小跨节点合同。

★ 这些 dataclass 是 Graph state 中可审计的“事实卡片”，而不是把 SQL/RAG 内部对象塞进顶层
State 的万能袋。调用者只需要认识请求、route 决定、Tool Observation 和最终结果四种对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.schemas.agent import ToolCallTrace
from engine.governance import TrustedCaller
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.trace.recorder import TraceStep

Route = Literal["sql", "rag", "none"]
ExecutionStatus = Literal["not_started", "completed", "external_unavailable", "failed"]
AnswerStatus = Literal[
    "complete", "partial", "clarification_required", "unsupported", "insufficient_evidence", "no_answer"
]
SafetyStatus = Literal["passed", "blocked"]
TerminationAction = Literal["answer", "clarify", "unsupported", "blocked", "failed"]


class HarnessContractError(ValueError):
    """Harness 收到不闭合的 route/observation 时抛出的合同错误。"""


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

    def __post_init__(self) -> None:
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

    def __post_init__(self) -> None:
        if self.route == "none" and self.needs_evidence:
            raise HarnessContractError("none route 不能请求 Evidence")
        if self.route != "none" and not self.needs_evidence:
            raise HarnessContractError("SQL/RAG route 必须请求 Evidence")
        if self.route == "rag" and self.requirement is None:
            raise HarnessContractError("RAG route 必须带受控 requirement")
        if self.route != "rag" and self.requirement is not None:
            raise HarnessContractError("只有 RAG route 可以携带 requirement")


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
        if self.route != self.route_decision.route:
            raise HarnessContractError("最终 route 必须与 RouteDecision 一致")
        if self.observation is not None and self.observation.route != self.route:
            raise HarnessContractError("Observation route 与最终 route 不一致")
        if self.observation is None and self.route != "none":
            raise HarnessContractError("需要 Tool 的 route 不能缺 Observation")
        if self.safety_status == "blocked" and not self.answer:
            raise HarnessContractError("blocked 结果仍必须有安全的用户文案")

