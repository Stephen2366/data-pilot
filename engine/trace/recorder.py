"""M5 JSONL Trace Recorder。

Trace 先写 JSONL，这是 phase2-plan 允许的主路径：字段结构先稳定，后续要迁到 SQLite 或
独立 AgentEvalOps 时，只替换存储层，不改 `/api/query` 响应契约。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent import CostInfo, ToolCallTrace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_PATH = PROJECT_ROOT / "eval" / "traces" / "traces.jsonl"


class TraceRecord(BaseModel):
    """一次 Agent 查询的完整 trace 行。

    字段设计贴近后续 EvalOps：评测只需要读取 question、route、sql、answer、safety_status、
    error_type 和 trace_id，就能判断每条 case 为什么通过或失败。
    """

    trace_id: str
    question: str
    user_role: str
    route: str
    answer: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    tables_used: list[str] = Field(default_factory=list)
    docs_used: list[dict[str, Any]] = Field(default_factory=list)
    chart_spec: dict[str, Any] | None = None
    safety_status: str
    blocked_reason: str | None = None
    cost: CostInfo
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    error_type: str | None = None


def append_trace(record: TraceRecord, *, path: Path = DEFAULT_TRACE_PATH) -> None:
    """把 trace 追加写入 JSONL。

    ★ 这里每行一个完整 JSON，方便 M6 直接按行读取；不在 M5 引入数据库迁移和查询接口。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(record.model_dump_json(ensure_ascii=False) + "\n")
