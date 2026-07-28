"""M5 JSONL Trace Recorder。

Trace 先写 JSONL，这是 phase2-plan 允许的主路径：字段结构先稳定，后续要迁到 SQLite 或
独立 EvalBench 时，只替换存储层，不改 `/api/query` 响应契约。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent import CostInfo, ToolCallTrace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_PATH = PROJECT_ROOT / "eval" / "traces" / "traces.jsonl"


class TraceStep(BaseModel):
    """M11 分步骤 trace 结构。

    ★ 这里不是把 pipeline 做成 DAG 引擎，而是先把“每一步发生了什么”固定成可评测字段。
    `parent_step_id` 和 `step_type` 为后续 Plan-and-Execute 预留；Phase 3A 仍只执行单条 SQL。
    """

    name: str
    step_index: int = Field(ge=1)
    step_type: str
    status: str
    input_summary: str = ""
    output_summary: str = ""
    latency_ms: float = Field(default=0.0, ge=0.0)
    error_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_step_id: str | None = None


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
    trace_steps: list[TraceStep] = Field(default_factory=list)
    error_type: str | None = None


def append_trace(record: TraceRecord, *, path: Path = DEFAULT_TRACE_PATH) -> None:
    """把 trace 追加写入 JSONL。

    ★ 这里每行一个完整 JSON，方便 M6 直接按行读取；不在 M5 引入数据库迁移和查询接口。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(record.model_dump_json(ensure_ascii=False) + "\n")
