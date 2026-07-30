"""M16B Trace Lifecycle：运行中收集 DataPilot steps，并可选写入 LangFuse live spans。

M16 的 LangFuse backend 是请求结束后把 `TraceRecord.trace_steps` 再拆成 flat spans。M16B
把埋点下沉到 pipeline / tool 的真实执行边界：业务代码只依赖这里的 DataPilot 抽象，不直接
import `langfuse`，后续换观测系统时不用污染 Text2SQL 主链路。
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Literal
from uuid import uuid4

from app.core.config import Settings, get_settings
from engine.trace.recorder import TraceStep

LangFuseWriteStatus = Literal["ok", "skipped", "failed"]
LangFuseSpanMode = Literal["post_hoc", "live"]


@dataclass(frozen=True)
class TraceLifecycleSnapshot:
    """Trace lifecycle 交给 API / TraceRecord 的只读快照。"""

    trace_steps: list[TraceStep]
    langfuse_trace_id: str | None
    langfuse_trace_url: str | None
    langfuse_write_status: LangFuseWriteStatus
    langfuse_span_mode: LangFuseSpanMode


class SpanHandle:
    """一个正在执行中的 DataPilot span。

    ★ 这个 handle 同时做两件事：
    1. 业务侧结束时生成一条 `TraceStep`，保证 JSONL/eval 仍有稳定结构；
    2. 如果 LangFuse live writer 可用，把同一个边界同步写成 LangFuse span。
    """

    def __init__(
        self,
        *,
        context: TraceContext,
        name: str,
        step_type: str,
        input_summary: str = "",
        metadata: dict[str, Any] | None = None,
        parent_step_id: str | None = None,
    ) -> None:
        self._context = context
        self._name = name
        self._step_type = step_type
        self._input_summary = input_summary
        self._metadata = metadata or {}
        self._parent_step_id = parent_step_id
        self._started_at = perf_counter()
        self._closed = False
        self._live_span = context._start_live_span(  # noqa: SLF001 - handle 是 lifecycle 内部协作者
            name=name,
            input_summary=input_summary,
            metadata=self._metadata,
            parent_step_id=parent_step_id,
        )

    def end(
        self,
        *,
        output_summary: str = "",
        status: str = "success",
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceStep:
        """结束成功或可预期状态的 span，并返回生成的 TraceStep。"""

        return self._finish(
            status=status,
            output_summary=output_summary,
            error_type=error_type,
            metadata=metadata,
        )

    def fail(
        self,
        *,
        output_summary: str,
        error_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceStep:
        """结束失败 span；异常由业务代码自己决定是否继续抛出或转 blocked。"""

        return self._finish(
            status="error",
            output_summary=output_summary,
            error_type=error_type,
            metadata=metadata,
        )

    def _finish(
        self,
        *,
        status: str,
        output_summary: str,
        error_type: str | None,
        metadata: dict[str, Any] | None,
    ) -> TraceStep:
        """生成 TraceStep，并把 live span 做 update/end。"""

        if self._closed:
            raise RuntimeError(f"trace span {self._name!r} has already been closed")

        self._closed = True
        merged_metadata = dict(self._metadata)
        if metadata:
            merged_metadata.update(metadata)

        step = self._context.record_step(
            name=self._name,
            step_type=self._step_type,
            status=status,
            input_summary=self._input_summary,
            output_summary=output_summary,
            latency_ms=_elapsed_ms(self._started_at),
            error_type=error_type,
            metadata=merged_metadata,
            parent_step_id=self._parent_step_id,
            live_span=self._live_span,
        )
        return step


class TraceContext:
    """一次 Text2SQL pipeline 的 lifecycle 容器。"""

    def __init__(
        self,
        *,
        datapilot_trace_id: str,
        question: str,
        user_role: str,
        live_writer: _LangFuseLiveWriter | None = None,
        initial_write_status: LangFuseWriteStatus = "skipped",
    ) -> None:
        self.datapilot_trace_id = datapilot_trace_id
        self.question = question
        self.user_role = user_role
        self._live_writer = live_writer
        self._langfuse_write_status: LangFuseWriteStatus = initial_write_status
        self._steps: list[TraceStep] = []

    @property
    def trace_steps(self) -> list[TraceStep]:
        """返回已记录 steps 的拷贝，避免调用方无意修改内部状态。"""

        return list(self._steps)

    def start_span(
        self,
        *,
        name: str,
        step_type: str | None = None,
        input_summary: str = "",
        metadata: dict[str, Any] | None = None,
        parent_step_id: str | None = None,
    ) -> SpanHandle:
        """开始一个运行中 span。"""

        return SpanHandle(
            context=self,
            name=name,
            step_type=step_type or name,
            input_summary=input_summary,
            metadata=metadata,
            parent_step_id=parent_step_id,
        )

    def record_step(
        self,
        *,
        name: str,
        step_type: str,
        status: str,
        input_summary: str = "",
        output_summary: str = "",
        latency_ms: float = 0.0,
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        parent_step_id: str | None = None,
        live_span: Any | None = None,
    ) -> TraceStep:
        """记录一个已完成 step；SQL tool 也用它在内部收口 guard / execution。"""

        step = TraceStep(
            name=name,
            step_index=len(self._steps) + 1,
            step_type=step_type,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            latency_ms=latency_ms,
            error_type=error_type,
            metadata=metadata or {},
            parent_step_id=parent_step_id,
        )
        self._steps.append(step)
        self._finish_live_span(live_span=live_span, step=step)
        return step

    def snapshot(
        self,
        *,
        status: str = "success",
        output_summary: str = "",
        error_type: str | None = None,
    ) -> TraceLifecycleSnapshot:
        """结束 root span、flush live writer，并返回 API 层可写入 TraceRecord 的字段。"""

        if self._live_writer is not None:
            try:
                self._live_writer.finish_root_span(
                    status=status,
                    output_summary=output_summary,
                    error_type=error_type,
                )
                self._live_writer.flush()
                if self._langfuse_write_status != "failed":
                    self._langfuse_write_status = "ok"
            except Exception:  # noqa: BLE001 - 可观测性失败不能影响业务结果
                self._langfuse_write_status = "failed"

        return TraceLifecycleSnapshot(
            trace_steps=self.trace_steps,
            langfuse_trace_id=self._live_writer.trace_id if self._live_writer is not None else None,
            langfuse_trace_url=self._live_writer.trace_url if self._live_writer is not None else None,
            langfuse_write_status=self._langfuse_write_status,
            langfuse_span_mode="live",
        )

    def _start_live_span(
        self,
        *,
        name: str,
        input_summary: str,
        metadata: dict[str, Any],
        parent_step_id: str | None,
    ) -> Any | None:
        """在 LangFuse 中启动 live span；失败只标记状态，不抛给业务链路。"""

        if self._live_writer is None:
            return None
        try:
            return self._live_writer.start_span(
                name=name,
                input_summary=input_summary,
                metadata=metadata,
                parent_step_id=parent_step_id,
            )
        except Exception:  # noqa: BLE001 - live span 是旁路观测
            self._langfuse_write_status = "failed"
            return None

    def _finish_live_span(self, *, live_span: Any | None, step: TraceStep) -> None:
        """更新并结束 LangFuse live span；失败只影响写入状态。"""

        if self._live_writer is None or live_span is None:
            return
        try:
            self._live_writer.finish_span(live_span, step=step)
        except Exception:  # noqa: BLE001 - live span 是旁路观测
            self._langfuse_write_status = "failed"


class _LangFuseLiveWriter:
    """LangFuse SDK 适配层，隐藏第三方 API 细节。"""

    def __init__(
        self,
        settings: Settings,
        *,
        datapilot_trace_id: str,
        question: str,
        user_role: str,
        client_factory: Callable[..., Any],
    ) -> None:
        self.settings = settings
        self.trace_id = uuid4().hex
        self.trace_url = self._trace_url(self.trace_id)
        self._client = client_factory(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
        )
        self._root_span = self._client.start_observation(
            trace_context={"trace_id": self.trace_id},
            name="datapilot-query",
            as_type="span",
            input={
                "question": question,
                "user_role": user_role,
            },
            metadata={"datapilot_trace_id": datapilot_trace_id},
        )
        self._root_closed = False

    def start_span(
        self,
        *,
        name: str,
        input_summary: str,
        metadata: dict[str, Any],
        parent_step_id: str | None,
    ) -> Any:
        """用 LangFuse SDK 4.x `start_observation` 创建 span。"""

        return self._client.start_observation(
            trace_context={"trace_id": self.trace_id},
            name=name,
            as_type="span",
            input={"summary": input_summary},
            metadata={
                "datapilot_step_metadata": metadata,
                "parent_step_id": parent_step_id,
            },
        )

    def finish_span(self, live_span: Any, *, step: TraceStep) -> None:
        """把 DataPilot TraceStep 字段同步到 LangFuse span，再关闭 span。"""

        if hasattr(live_span, "update"):
            live_span.update(
                output={"summary": step.output_summary, "status": step.status},
                metadata={
                    "step_index": step.step_index,
                    "step_type": step.step_type,
                    "status": step.status,
                    "latency_ms": step.latency_ms,
                    "error_type": step.error_type,
                    "parent_step_id": step.parent_step_id,
                    "metadata": step.metadata,
                },
            )
        live_span.end()

    def finish_root_span(self, *, status: str, output_summary: str, error_type: str | None) -> None:
        """结束请求级 root span；它只存在于 LangFuse，不进入 JSONL trace_steps。"""

        if self._root_closed:
            return
        self._root_closed = True
        if hasattr(self._root_span, "update"):
            self._root_span.update(
                output={"summary": output_summary, "status": status},
                metadata={"status": status, "error_type": error_type},
            )
        self._root_span.end()

    def flush(self) -> None:
        """把 SDK 队列 flush 到 LangFuse。"""

        self._client.flush()

    def _trace_url(self, langfuse_trace_id: str) -> str:
        """生成与 M16 backend 一致的 trace URL。"""

        return f"{self.settings.langfuse_base_url.rstrip('/')}/project/traces/{langfuse_trace_id}"


def build_trace_context(
    *,
    trace_id: str,
    question: str,
    user_role: str,
    settings: Settings | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> TraceContext:
    """构造一次 pipeline lifecycle；LangFuse 不可用时自动降级为只收集 TraceStep。"""

    resolved_settings = settings or get_settings()
    if not resolved_settings.langfuse_enabled:
        return TraceContext(
            datapilot_trace_id=trace_id,
            question=question,
            user_role=user_role,
            initial_write_status="skipped",
        )

    if not resolved_settings.langfuse_public_key or not resolved_settings.langfuse_secret_key:
        return TraceContext(
            datapilot_trace_id=trace_id,
            question=question,
            user_role=user_role,
            initial_write_status="failed",
        )

    try:
        if client_factory is None:
            from langfuse import Langfuse

            client_factory = Langfuse

        live_writer = _LangFuseLiveWriter(
            resolved_settings,
            datapilot_trace_id=trace_id,
            question=question,
            user_role=user_role,
            client_factory=client_factory,
        )
    except Exception:  # noqa: BLE001 - 构造 SDK 失败也只影响观测
        return TraceContext(
            datapilot_trace_id=trace_id,
            question=question,
            user_role=user_role,
            initial_write_status="failed",
        )

    return TraceContext(
        datapilot_trace_id=trace_id,
        question=question,
        user_role=user_role,
        live_writer=live_writer,
        initial_write_status="skipped",
    )


def _elapsed_ms(started_at: float) -> float:
    """返回保留 3 位小数的毫秒耗时。"""

    return round((perf_counter() - started_at) * 1000, 3)
