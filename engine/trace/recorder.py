"""M5/M16 Trace Recorder：JSONL 主链路 + 可选 LangFuse 旁路。

Trace 先写 JSONL，这是 phase2-plan 允许的主路径：字段结构先稳定，后续要迁到 SQLite 或
独立 EvalBench 时，只替换存储层，不改 `/api/query` 响应契约。

M16 在这个基础上加了一层 TraceRouter：`append_trace()` 这个老入口不变，但内部可以同时
调多个 backend。默认仍只有 JSONL；只有显式开启 `LANGFUSE_ENABLED=true` 时，才追加写入
LangFuse。这样新观测系统坏掉时，原来的本地 trace 和 eval 仍然可用。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.schemas.agent import CostInfo, ToolCallTrace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_PATH = PROJECT_ROOT / "eval" / "traces" / "traces.jsonl"
logger = logging.getLogger(__name__)


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

    ★ M16 新增的 LangFuse 字段只属于 trace 存储层：它们会进入 JSONL，方便反查 Cloud trace，
    但不会进入 `/api/query` 的 AgentResponse，避免第三方观测系统改变 API 契约。
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
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None
    langfuse_write_status: Literal["ok", "skipped", "failed"] = "skipped"


class TraceBackend(Protocol):
    """Trace 存储后端协议。

    ★ 类比 Java 里的 interface：TraceRouter 只关心 backend 有 `record()` 方法，不关心它背后
    是写 JSONL、写 LangFuse，还是以后写 SQLite / EvalBench。
    """

    name: str

    def record(self, record: TraceRecord, *, path: Path | None = None) -> None:
        """写入一条 trace；`path` 只对本地 JSONL backend 有意义。"""


class JSONLBackend:
    """本地 JSONL trace 后端。

    这是 DataPilot 的主路和兜底：无论 LangFuse 是否启用、是否报错，最终都应该能在 JSONL
    里看到本次请求的 trace。
    """

    name = "jsonl"

    def record(self, record: TraceRecord, *, path: Path | None = None) -> None:
        """把 trace 追加写入 JSONL，保留 M5 以来的“一行一个完整 JSON”格式。"""

        resolved_path = path or DEFAULT_TRACE_PATH
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        with resolved_path.open("a", encoding="utf-8") as file:
            file.write(record.model_dump_json(ensure_ascii=False) + "\n")


class TraceRouter:
    """把同一条 TraceRecord 分发给多个后端。

    ★ M16 的关键点是“旁路增强，不替代主链路”：LangFuse backend 失败时只记录 warning，
    后面的 JSONLBackend 仍继续执行，避免观测系统把 API 请求拖成 500。
    """

    def __init__(self, backends: list[TraceBackend]) -> None:
        self.backends = backends

    def record(self, record: TraceRecord, *, path: Path | None = None) -> None:
        """按顺序写入所有 backend，并隔离单个 backend 的失败。"""

        for backend in self.backends:
            try:
                backend.record(record, path=path)
            except Exception as exc:  # noqa: BLE001 - trace 旁路必须兜住所有外部 backend 异常
                if backend.name == "langfuse":
                    record.langfuse_write_status = "failed"
                logger.warning("trace backend %s failed: %s", backend.name, exc)


def build_trace_router(settings: Settings | None = None) -> TraceRouter:
    """按 Settings 构建 TraceRouter。

    ★ 这里刻意把 LangFuse backend 放在 JSONLBackend 前面：LangFuse 成功或失败后回填的
    `langfuse_trace_id/langfuse_write_status` 才能写进同一行 JSONL，方便后续 eval / smoke 反查。
    """

    resolved_settings = settings or get_settings()
    backends: list[TraceBackend] = []
    if resolved_settings.langfuse_enabled:
        # 延迟导入：LANGFUSE_ENABLED=false 时，即使本地没安装 langfuse SDK，原链路也能启动。
        from engine.trace.langfuse_backend import LangFuseBackend

        backends.append(LangFuseBackend(resolved_settings))
    backends.append(JSONLBackend())
    return TraceRouter(backends)


trace_router = build_trace_router()


def configure_trace_router(router: TraceRouter) -> None:
    """替换模块级 router，供测试 / smoke 在同一进程内切换 LangFuse 开关。"""

    global trace_router
    trace_router = router


def append_trace(record: TraceRecord, *, path: Path = DEFAULT_TRACE_PATH) -> None:
    """兼容旧入口：调用方仍用 append_trace，内部交给 TraceRouter。"""

    trace_router.record(record, path=path)
