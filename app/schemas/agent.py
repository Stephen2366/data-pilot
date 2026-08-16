"""Agent 查询接口 Schema：M5 扩展版 AgentResponse 的单一实现。

★ 从 `/api/query` 第一次落地开始就用 Pydantic Schema 固定响应形状，后续 M5 只能增量
扩展字段，不能推倒重来。这里保留 M3/M4 已有字段含义，再补 EvalOps 和演示页需要的
成本、工具调用、文档命中和图表结构。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    """M5 扩展版 AgentResponse。

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
