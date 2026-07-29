"""LangFuse trace backend：把 DataPilot TraceRecord 写入 LangFuse Cloud / self-host。

M16 只做旁路观测，不让 LangFuse 接管 DataPilot 的请求级 `trace_id`。这里会生成独立
`langfuse_trace_id`，并在 metadata 中保存 `datapilot_trace_id`，后续 M17 score 回写也只按
LangFuse trace id 关联。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.core.config import Settings
from engine.trace.recorder import TraceRecord


class LangFuseBackend:
    """把 TraceRecord 映射成 LangFuse flat spans。

    ★ 这里不伪造嵌套 span 和真实时间线：当前 TraceRecord 是请求结束后一次性生成的快照，
    只有每步 latency，没有每步 started_at / ended_at。RAG/Hybrid 阶段如果 pipeline 埋点下沉，
    再用 `parent_step_id` 生成更精确的 DAG / span tree。
    """

    name = "langfuse"

    def __init__(self, settings: Settings, *, client_factory: Callable[..., Any] | None = None) -> None:
        self.settings = settings
        self.client_factory = client_factory

    def record(self, record: TraceRecord, *, path: Path | None = None) -> None:
        """写入 LangFuse，并回填 `langfuse_trace_id/url/status`。

        `path` 是 JSONLBackend 的参数，对 LangFuse 没有意义。外部 SDK、网络或配置错误直接抛出，
        由 TraceRouter 捕获并降级，确保 JSONL 主链路继续写入。
        """

        if record.langfuse_span_mode == "live":
            # M16B：pipeline/tool 已经在真实执行边界写过 live spans，这里不能再按 M16 方式
            # post-hoc 重放，否则 LangFuse 里会出现两套同名 step。
            if record.langfuse_trace_id is not None and record.langfuse_trace_url is None:
                record.langfuse_trace_url = self._trace_url(record.langfuse_trace_id)
            return

        client = self._build_client()
        langfuse_trace_id = record.langfuse_trace_id or uuid4().hex
        record.langfuse_trace_id = langfuse_trace_id
        record.langfuse_trace_url = self._trace_url(langfuse_trace_id)

        # 步骤 1：写请求级 root span ==========================================================
        # root span 只放最小必要信息，不上传完整 rows/docs，避免把 Cloud trace 变成敏感数据副本。
        root_span = client.start_observation(
            trace_context={"trace_id": langfuse_trace_id},
            name="datapilot-query",
            as_type="span",
            input={
                "question": record.question,
                "user_role": record.user_role,
                "route": record.route,
            },
            output={
                "answer": record.answer,
                "safety_status": record.safety_status,
                "blocked_reason": record.blocked_reason,
                "error_type": record.error_type,
            },
            metadata=self._record_metadata(record),
        )
        root_span.end()

        # 步骤 2：写 flat step spans ===========================================================
        # 每个 TraceStep 都挂在同一个 trace_id 下，但不设置 parent，避免伪造当前没有的数据。
        for step in record.trace_steps:
            step_span = client.start_observation(
                trace_context={"trace_id": langfuse_trace_id},
                name=step.name,
                as_type="span",
                input={"summary": step.input_summary},
                output={"summary": step.output_summary, "status": step.status},
                metadata={
                    "datapilot_trace_id": record.trace_id,
                    "step_index": step.step_index,
                    "step_type": step.step_type,
                    "status": step.status,
                    "latency_ms": step.latency_ms,
                    "error_type": step.error_type,
                    "parent_step_id": step.parent_step_id,
                    "metadata": step.metadata,
                },
            )
            step_span.end()

        # 步骤 3：flush 确保送达 API ===========================================================
        # flush 不保证 Cloud 查询立即可见；它只说明 SDK 队列已经把事件送出。
        client.flush()
        record.langfuse_write_status = "ok"

    def _build_client(self) -> Any:
        """按 M15 固定的 SDK 4.x API 构造 LangFuse client。"""

        if not self.settings.langfuse_public_key or not self.settings.langfuse_secret_key:
            raise RuntimeError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required when LangFuse is enabled")

        if self.client_factory is None:
            # 延迟导入：只有真正启用并写入 LangFuse 时才要求安装 SDK。
            from langfuse import Langfuse

            factory = Langfuse
        else:
            factory = self.client_factory

        return factory(
            public_key=self.settings.langfuse_public_key,
            secret_key=self.settings.langfuse_secret_key,
            base_url=self.settings.langfuse_base_url,
        )

    def _trace_url(self, langfuse_trace_id: str) -> str:
        """生成调试 URL；不查询 project id，避免 URL 生成依赖额外 Cloud API。"""

        return f"{self.settings.langfuse_base_url.rstrip('/')}/project/traces/{langfuse_trace_id}"

    def _record_metadata(self, record: TraceRecord) -> dict[str, Any]:
        """整理请求级 metadata，控制 Cloud payload 体积和敏感面。"""

        return {
            "datapilot_trace_id": record.trace_id,
            "columns": record.columns,
            "tables_used": record.tables_used,
            "docs_count": len(record.docs_used),
            "rows_count": len(record.rows),
            "tool_count": len(record.tool_calls),
            "trace_step_count": len(record.trace_steps),
            "cost": record.cost.model_dump(mode="json"),
            "chart_type": (record.chart_spec or {}).get("mark") if record.chart_spec else None,
        }
