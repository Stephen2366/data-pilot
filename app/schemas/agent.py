"""Agent 查询接口 Schema：从 M5 单轮增量演进到 M37 bounded thread/turn 投影。

★ 从 `/api/query` 第一次落地开始就用 Pydantic Schema 固定响应形状，后续 M5 只能增量
扩展字段，不能推倒重来。这里保留 M3/M4 已有字段含义，再补 EvalOps 和演示页需要的
成本、工具调用、文档命中和图表结构。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskRequestEnvelope(BaseModel):
    """M43 新 task family 的严格信封；delta/state/route/evidence 均不能由客户端提交。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["start", "continue", "switch", "cancel"]
    task_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "TaskRequestEnvelope":
        """固定 start 与已有 task identity 的互斥形状，拒绝半截 resume。"""

        has_identity = self.task_id is not None and self.expected_version is not None
        if (self.task_id is None) != (self.expected_version is None):
            raise ValueError("task_id 与 expected_version 必须同时提供")
        if self.action == "start" and has_identity:
            raise ValueError("start 不得提交已有 task identity")
        if self.action != "start" and not has_identity:
            raise ValueError("continue/switch/cancel 必须提交 task identity")
        return self


class QueryRequest(BaseModel):
    """自然语言查询请求。

    `user_role` 在 M35 起只表示请求者选择的 active role：应用组装层必须先通过 caller
    resolver 把它解析为可信 fixture / authenticated caller，才能进入 SQL Guard 或知识 ACL。
    `force_new_pipeline` 是新旧 Text2SQL 的兼容开关：默认 True，让普通 API 与 M27 Eval 都走
    Schema Retrieval → QueryPlan → SQL Guard 的新 pipeline；显式传 False 才暂时回到 legacy
    baseline，供兼容排障使用。
    `schema_retrieval_profile` 是本地实验开关：默认不传时沿用环境变量；演示页可显式选择
    Milvus + Qwen embedding，方便 Phase 3 RAG / Hybrid 前手动对比。
    `schema_fusion_strategy` 是 M21 的受控实验开关：默认 `weighted` 保持既有排序，只有显式
    传 `rrf` 才会改用 rank-based fusion；它不改变默认检索或响应契约。
    """

    question: str = Field(min_length=1)
    user_role: str = Field(default="ops")
    force_new_pipeline: bool = Field(default=True)
    schema_retrieval_profile: Literal["default", "milvus_qwen37"] = Field(default="default")
    schema_fusion_strategy: Literal["weighted", "rrf"] = Field(default="weighted")
    # M36/M37：thread id/version 与 clarification/follow-up payload 必须形成互斥闭集。
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_version: int | None = Field(default=None, ge=1)
    clarification_answers: dict[str, str] = Field(default_factory=dict)
    enable_bounded_follow_up: bool = Field(default=False)
    follow_up_action: Literal["adjust_sql_scope", "explain_same_evidence", "ask_related_evidence"] | None = None
    follow_up_fields: dict[str, str] = Field(default_factory=dict)
    # M43：有 task 信封才进入 Agent task family；省略时完整保留 M35–M42 行为。
    task: TaskRequestEnvelope | None = None

    @model_validator(mode="after")
    def validate_resume_shape(self) -> "QueryRequest":
        """拒绝半截 resume，避免 API 猜测这是新问题还是旧任务补充。"""

        has_thread = self.thread_id is not None
        if self.task is not None and (
            has_thread or self.clarification_answers or self.follow_up_action is not None
            or self.follow_up_fields or self.enable_bounded_follow_up
        ):
            raise ValueError("task family 与 legacy thread/follow-up payload 互斥")
        if self.task is not None:
            return self
        if has_thread != (self.expected_version is not None):
            raise ValueError("thread_id 与 expected_version 必须同时提供")
        is_resume = bool(self.clarification_answers)
        is_follow_up = self.follow_up_action is not None
        if is_resume and is_follow_up:
            raise ValueError("clarification resume 与 follow-up 不能同时提交")
        if has_thread != (is_resume or is_follow_up):
            raise ValueError("thread request 必须提交 clarification_answers 或 follow_up_action")
        if not is_follow_up and self.follow_up_fields:
            raise ValueError("只有 follow-up request 可以提供 follow_up_fields")
        if has_thread and self.enable_bounded_follow_up:
            raise ValueError("enable_bounded_follow_up 只允许 initial request 提供")
        return self


class ClarificationFieldView(BaseModel):
    """客户端可填写的单个 closed-world clarification 字段。"""

    key: str
    label: str
    value_type: Literal["text", "time_range", "enum"]
    allowed_values: list[str] = Field(default_factory=list)
    max_length: int = Field(gt=0)


class ClarificationView(BaseModel):
    """首次 pending 响应中的待补说明，不含任何已填写 value。"""

    identity: str
    prompt: str
    fields: list[ClarificationFieldView]


class FollowUpActionView(BaseModel):
    """成功回答后客户端可选择的一种受控追问动作。"""

    action: Literal["adjust_sql_scope", "explain_same_evidence", "ask_related_evidence"]
    label: str
    fields: list[ClarificationFieldView]


class FollowUpView(BaseModel):
    """服务端签发的 follow-up 表单合同。"""

    identity: str
    actions: list[FollowUpActionView]


class ThreadView(BaseModel):
    """合法 owner 可见的 thread/checkpoint 安全投影。"""

    thread_id: str
    checkpoint_version: int = Field(ge=1)
    state_version: str
    status: Literal["pending", "claimed", "follow_up_ready", "follow_up_claimed", "resolved", "cleared"]
    expires_at: str
    clarification: ClarificationView | None = None
    follow_up: FollowUpView | None = None
    follow_up_budget_remaining: int = Field(default=0, ge=0, le=1)


class ThreadControlResponse(BaseModel):
    """显式清理 thread 的结果；失败时不返回 raw thread 投影。"""

    ok: bool
    reason_code: str
    safety_status: Literal["passed", "blocked"]
    message: str
    thread: ThreadView | None = None


class TaskView(BaseModel):
    """合法 owner 可见的 task 安全投影；不包含 owner 比较值、rows 或历史答案。"""

    task_id: str
    task_version: int = Field(ge=1)
    status: Literal["claimed", "active", "cancelled", "switched", "cleared"]
    expires_at: str
    state: dict[str, Any]


class TaskControlResponse(BaseModel):
    """task clear 的闭合响应；失败不回显 task 状态。"""

    ok: bool
    reason_code: str
    safety_status: Literal["passed", "blocked"]
    message: str
    task: TaskView | None = None


class CostInfo(BaseModel):
    """一次 Agent 查询的成本与耗时快照。

    ★ M5 先不做真实计费，只固定字段：模型名和 token 默认为空 / 0；SQL 耗时与总耗时真实记录。
    后续接入更完整 LLM usage 时，只需要填充这些字段，不改响应契约。
    """

    latency_ms: float = Field(default=0.0, ge=0.0)
    sql_time_ms: float = Field(default=0.0, ge=0.0)
    model: str | None = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class ToolCallTrace(BaseModel):
    """单次工具调用记录，供响应体和 JSONL trace 共用。

    类比 LangGraph / Agent 工程里的 tool call 日志：它不是给用户看的答案，而是给评测、
    调试和演示页解释“刚才调用了什么工具、花了多久、是否被拦截”。
    """

    tool_name: str
    status: Literal["success", "blocked", "error", "skipped"]
    latency_ms: float = Field(default=0.0, ge=0.0)
    sql: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    error_type: str | None = None
    message: str | None = None


class AgentResponse(BaseModel):
    """查询结果的兼容响应；M36/M37 只增量加入 bounded turn/thread 字段。

    字段顺序按“路由 → 答案 → 证据 → 图表 → 安全 → 成本 / 追踪”组织，方便前端和
    EvalOps 读取。旧字段只增不改，避免 M3/M4 测试和后续调用方失效。
    """

    route: Literal["sql", "rag", "hybrid", "none"]
    answer: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    tables_used: list[str] = Field(default_factory=list)
    docs_used: list[dict[str, Any]] = Field(default_factory=list)
    chart_spec: dict[str, Any] | None = None
    safety_status: Literal["passed", "blocked"]
    blocked_reason: str | None = None
    cost: CostInfo = Field(default_factory=CostInfo)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    error_type: str | None = None
    trace_id: str
    # M35 四轴新增字段。旧字段继续保留为兼容投影，不能反向驱动 Harness controller。
    execution_status: Literal["not_started", "completed", "external_unavailable", "failed"] = "not_started"
    answer_status: Literal[
        "complete", "partial", "clarification_required", "unsupported", "insufficient_evidence", "no_answer"
    ] = "no_answer"
    citations: list[dict[str, Any]] = Field(default_factory=list)
    reason_code: str | None = None
    # M36/M37：无 thread 的旧请求保持 None/initial；bounded turn 才返回增量字段。
    turn_action: Literal["initial", "resume", "follow_up", "rejected"] = "initial"
    graph_invocation_count: int = Field(default=1, ge=0, le=1)
    thread: ThreadView | None = None
    # M38：只给出 branch 的安全状态与已验证引用，不把私有 typed Evidence 塞回 API。
    hybrid_branches: list[dict[str, Any]] = Field(default_factory=list)
    # M43：只在 nested task envelope 路径填充；旧调用方得到稳定默认值。
    runtime_family: Literal["legacy", "agent_task"] = "legacy"
    task_action: Literal["start", "continue", "switch", "cancel", "rejected"] | None = None
    task_runtime_invocation_count: int = Field(default=0, ge=0, le=1)
    task: TaskView | None = None
    task_delta: dict[str, Any] | None = None
    task_transition: dict[str, Any] | None = None
    node_contexts: list[dict[str, Any]] = Field(default_factory=list)
    # M44：task-only additive B2 facts；legacy response 保持空投影。
    action_attempts: list[dict[str, Any]] = Field(default_factory=list)
    agent_budget: dict[str, Any] | None = None
    agent_termination: dict[str, Any] | None = None
    knowledge_runtimes: list[dict[str, str]] = Field(default_factory=list)
    agent_loop_runtime: dict[str, Any] | None = None
    # M46：API/Trace/Agent Scenario v4 对同一安全父子账投影的不可逆对账值。
    agent_scenario_source_identity: str | None = None
