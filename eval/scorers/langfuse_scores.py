"""M17 LangFuse Score 回写：把本地 scorer 明细附到 Cloud trace 上。

这里不查询 trace 是否已经可见。M16/M16B 已经把 `langfuse_trace_id` 写进 JSONL；M17 只按
这个 ID 调 `create_score()`，查询延迟留给 smoke/debug。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from app.core.config import Settings, get_settings
from engine.trace.langfuse_safe_projection import project_score
from eval.scorers.base import EvalScoreDetail, LangFuseScorePayload

logger = logging.getLogger(__name__)


class LangFuseScoreWriter:
    """把 score payload 写入 LangFuse，失败时只返回 failed 数，不抛业务异常。"""

    def __init__(self, settings: Settings | None = None, *, client_factory: Callable[..., Any] | None = None) -> None:
        self.settings = settings or get_settings()
        self.client_factory = client_factory

    def write_scores(self, payloads: list[LangFuseScorePayload]) -> dict[str, int]:
        """批量写 score，返回 ok/skipped/failed 计数。"""

        if not payloads:
            return {"ok": 0, "skipped": 0, "failed": 0}
        if not self.settings.langfuse_enabled or not self.settings.langfuse_public_key or not self.settings.langfuse_secret_key:
            return {"ok": 0, "skipped": len(payloads), "failed": 0}

        try:
            client = self._build_client()
        except Exception as exc:  # noqa: BLE001 - score 回写不能阻断 eval
            logger.warning("langfuse score client unavailable: %s", exc)
            return {"ok": 0, "skipped": 0, "failed": len(payloads)}

        ok = 0
        failed = 0
        for payload in payloads:
            try:
                client.create_score(**project_score(payload))
                ok += 1
            except Exception as exc:  # noqa: BLE001 - 单条 score 失败不影响其他 score
                logger.warning("langfuse score write failed name=%s trace_id=%s: %s", payload.name, payload.trace_id, exc)
                failed += 1
        try:
            client.flush()
        except Exception as exc:  # noqa: BLE001 - flush 失败表示本批次不能确认送达
            logger.warning("langfuse score flush failed: %s", exc)
            failed += ok
            ok = 0
        return {"ok": ok, "skipped": 0, "failed": failed}

    def _build_client(self) -> Any:
        """延迟构造 SDK client；LANGFUSE_ENABLED=false 时不会 import SDK。"""

        if self.client_factory is None:
            from langfuse import Langfuse

            factory = Langfuse
        else:
            factory = self.client_factory
        return factory(
            public_key=self.settings.langfuse_public_key,
            secret_key=self.settings.langfuse_secret_key,
            base_url=self.settings.langfuse_base_url,
        )


def build_langfuse_score_payloads(
    *,
    results: list[Any],
    trace_path: Path,
) -> list[LangFuseScorePayload]:
    """从 EvalResult + JSONL trace 映射生成 LangFuse score payloads。"""

    trace_id_map = _load_langfuse_trace_id_map(trace_path)
    payloads: list[LangFuseScorePayload] = []
    for result in results:
        if not result.trace_id:
            continue
        langfuse_trace_id = trace_id_map.get(result.trace_id)
        if not langfuse_trace_id:
            continue
        for detail in result.score_details:
            payload = _detail_to_payload(detail, langfuse_trace_id=langfuse_trace_id, case_id=result.case.case_id)
            if payload is not None:
                payloads.append(payload)
    return payloads


def _load_langfuse_trace_id_map(trace_path: Path) -> dict[str, str]:
    """读取 JSONL trace，建立 DataPilot trace_id -> LangFuse trace_id 映射。"""

    if not trace_path.exists():
        return {}
    mapping: dict[str, str] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        datapilot_trace_id = record.get("trace_id")
        langfuse_trace_id = record.get("langfuse_trace_id")
        if datapilot_trace_id and langfuse_trace_id and record.get("langfuse_write_status") == "ok":
            mapping[str(datapilot_trace_id)] = str(langfuse_trace_id)
    return mapping


def _detail_to_payload(
    detail: EvalScoreDetail,
    *,
    langfuse_trace_id: str,
    case_id: str,
) -> LangFuseScorePayload | None:
    """把可量化 detail 转成 LangFuse numeric score；skipped/null 不写。"""

    if detail.value is None or detail.skipped:
        return None
    return LangFuseScorePayload(
        trace_id=langfuse_trace_id,
        name=detail.name,
        value=detail.value,
        data_type="NUMERIC",
        # ★ reason、issue_tags 与 scorer 自由 metadata 仍属于本地诊断正文，
        # Cloud 只接收稳定身份和布尔状态；project_score 会再做一次 allowlist 校验。
        comment="",
        metadata={
            "case_id": case_id,
            "scorer_id": detail.name,
            "passed": detail.passed,
            "review_required": detail.review_required,
        },
    )
