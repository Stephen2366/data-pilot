"""Agent 查询接口 Schema：M3 简化版 AgentResponse 的单一实现。

★ 从 `/api/query` 第一次落地开始就用 Pydantic Schema 固定响应形状，后续 M5 只能增量
扩展字段，不能推倒重来。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """自然语言查询请求。

    `user_role` 在 M3 只透传保留；M4 会把它接入 RBAC 权限矩阵。
    """

    question: str = Field(min_length=1)
    user_role: str = Field(default="ops")


class AgentResponse(BaseModel):
    """M3 简化版 AgentResponse。

    字段顺序按“路由 → 答案 → SQL → 表格 → 安全 → 追踪”组织，方便前端和 EvalOps 读取。
    """

    route: Literal["sql", "rag", "hybrid"]
    answer: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    safety_status: Literal["passed", "blocked"]
    blocked_reason: str | None = None
    trace_id: str

