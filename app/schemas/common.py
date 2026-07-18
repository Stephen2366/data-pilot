from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    """统一分页响应。

    ★ 后续演示页和 EvalOps 可以稳定读取 `items / total / page / page_size`，
    不需要为每个列表接口写一套解析逻辑。
    """

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    trace_id: str


class ErrorResponse(BaseModel):
    """统一错误响应，避免把 FastAPI / Python 内部异常直接暴露给前端。"""

    code: str
    message: str
    trace_id: str
    details: list[dict] | dict | None = None
