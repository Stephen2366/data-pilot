"""DataPilot -> Langfuse 的唯一安全投影。

本模块只接受有限、可枚举的运行事实。question/answer/SQL/rows、输入输出摘要、文档正文、
绝对路径、凭据和任意 metadata 都没有进入 Cloud payload 的通道。★ 未登记字段直接抛错，
由调用侧的 sidecar 边界转成 ``failed``；本地 JSONL 仍保存它原本获准保存的事实。
"""

from __future__ import annotations

import math
import re
from typing import Any


PROJECTION_VERSION = "datapilot-langfuse-safe-v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ABSOLUTE_WINDOWS = re.compile(r"^[A-Za-z]:[\\/]")
_CREDENTIAL_MARKERS = ("sk-", "authorization", "api_key", "secret_key", "password", "bearer ")

_ROUTES = {"sql", "rag", "hybrid", "blocked", "unknown"}
_EXECUTION_STATUSES = {
    "not_started", "completed", "rejected", "blocked", "failed", "pipeline_error",
    "external_unavailable", "clarification_required", "cancelled",
}
_ANSWER_STATUSES = {"no_answer", "answered", "blocked", "failed", "partial", "clarification_required"}
_SAFETY_STATUSES = {"passed", "blocked", "failed", "not_checked", "unknown"}
_STEP_STATUSES = {"success", "passed", "completed", "blocked", "error", "failed", "skipped", "not_observed"}
_ERROR_TYPES = {
    None, "sql_guard_blocked", "llm_generation_error", "query_plan_error", "schema_retrieval_error",
    "sql_execution_error", "output_contract_error", "external_unavailable", "network_error", "timeout",
    "provider_unavailable", "validation_error", "unexpected_error",
}

# metadata 只允许布尔、有限枚举或有限数值。列表、正文、表/列/文档名和错误消息都不允许。
_BOOLEAN_METADATA = {
    "passed", "review_required", "has_chart", "cache_hit", "reused", "authorized", "grounded",
}
_NUMERIC_METADATA = {
    "step_index", "latency_ms", "row_count", "column_count", "trace_step_count", "physical_attempts",
    "replicate_id", "merged_hit_count", "candidate_count", "selected_count", "tool_count", "docs_count",
}
_IDENTITY_METADATA = {
    "case_id", "scenario_id", "scorer_id", "scorer_version", "contract_version", "runtime_family",
    "parent_step_id", "step_type", "status", "error_type", "route", "execution_status", "answer_status",
    "safety_status", "span_mode", "mark", "guard_stage", "blocked_via", "error_subtype", "provider",
}
_ALLOWED_METADATA = _BOOLEAN_METADATA | _NUMERIC_METADATA | _IDENTITY_METADATA


class LangfuseProjectionError(ValueError):
    """安全投影拒绝：只应在 Langfuse sidecar 边界被隔离。"""


def project_root(
    *,
    trace_id: str,
    datapilot_trace_id: str,
    route: str | None = None,
    execution_status: str | None = None,
    answer_status: str | None = None,
    safety_status: str | None = None,
    trace_step_count: int | None = None,
) -> dict[str, Any]:
    """构造 root observation；刻意没有 input/output 参数。"""

    metadata: dict[str, Any] = {"datapilot_trace_id": _opaque(datapilot_trace_id, "datapilot_trace_id")}
    _optional_enum(metadata, "route", route, _ROUTES)
    _optional_enum(metadata, "execution_status", execution_status, _EXECUTION_STATUSES)
    _optional_enum(metadata, "answer_status", answer_status, _ANSWER_STATUSES)
    _optional_enum(metadata, "safety_status", safety_status, _SAFETY_STATUSES)
    if trace_step_count is not None:
        metadata["trace_step_count"] = _finite_nonnegative(trace_step_count, "trace_step_count")
    return {
        "trace_context": {"trace_id": _opaque(trace_id, "trace_id")},
        "name": "datapilot-query",
        "as_type": "span",
        "metadata": {"projection_version": PROJECTION_VERSION, **metadata},
    }


def project_observation_start(
    *,
    trace_id: str,
    name: str,
    step_type: str,
    parent_span_id: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """构造 child observation，并把真实 Langfuse root span ID 作为 parent。"""

    trace_context = {"trace_id": _opaque(trace_id, "trace_id")}
    if parent_span_id is not None:
        trace_context["parent_span_id"] = _opaque(parent_span_id, "parent_span_id")
    projected = _project_metadata(metadata or {})
    projected["step_type"] = _identifier(step_type, "step_type")
    return {
        "trace_context": trace_context,
        "name": _identifier(name, "name"),
        "as_type": "span",
        "metadata": {"projection_version": PROJECTION_VERSION, **projected},
    }


def project_observation_finish(*, step: Any) -> dict[str, Any]:
    """把本地 TraceStep 投影为 update；summary 永远不进入参数。"""

    status = str(step.status)
    if status not in _STEP_STATUSES:
        raise LangfuseProjectionError(f"status is not allowlisted: {status!r}")
    metadata = {
        "step_index": _finite_nonnegative(step.step_index, "step_index"),
        "step_type": _identifier(step.step_type, "step_type"),
        "status": status,
        "latency_ms": _finite_nonnegative(step.latency_ms, "latency_ms"),
        **_project_metadata(dict(step.metadata)),
    }
    if step.error_type is not None:
        if step.error_type not in _ERROR_TYPES:
            raise LangfuseProjectionError(f"error_type is not allowlisted: {step.error_type!r}")
        metadata["error_type"] = step.error_type
    if step.parent_step_id is not None:
        metadata["parent_step_id"] = _identifier(step.parent_step_id, "parent_step_id")
    return {"metadata": {"projection_version": PROJECTION_VERSION, **metadata}}


def project_root_finish(*, status: str, error_type: str | None) -> dict[str, Any]:
    """结束 root 时只发送枚举状态，不发送 answer/output summary。"""

    if status not in _STEP_STATUSES:
        raise LangfuseProjectionError(f"status is not allowlisted: {status!r}")
    metadata: dict[str, Any] = {"status": status}
    if error_type is not None:
        if error_type not in _ERROR_TYPES:
            raise LangfuseProjectionError(f"error_type is not allowlisted: {error_type!r}")
        metadata["error_type"] = error_type
    return {"metadata": {"projection_version": PROJECTION_VERSION, **metadata}}


def project_score(payload: Any) -> dict[str, Any]:
    """构造 4.15.1 ``create_score`` 参数；自由 comment 被完全省略。"""

    if payload.data_type != "NUMERIC" or not isinstance(payload.value, (int, float)) or isinstance(payload.value, bool):
        raise LangfuseProjectionError("DataPilot score must be numeric")
    value = float(payload.value)
    if not math.isfinite(value):
        raise LangfuseProjectionError("score value must be finite")
    return {
        "trace_id": _opaque(payload.trace_id, "trace_id"),
        "name": _identifier(payload.name, "score name"),
        "value": value,
        "data_type": "NUMERIC",
        "metadata": {"projection_version": PROJECTION_VERSION, **_project_metadata(dict(payload.metadata))},
    }


def _project_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    unknown = set(metadata) - _ALLOWED_METADATA
    if unknown:
        raise LangfuseProjectionError(f"unknown Langfuse metadata keys: {sorted(unknown)}")
    projected: dict[str, Any] = {}
    for key, value in metadata.items():
        _reject_sensitive_value(value, key)
        if key in _BOOLEAN_METADATA:
            if not isinstance(value, bool):
                raise LangfuseProjectionError(f"{key} must be boolean")
            projected[key] = value
        elif key in _NUMERIC_METADATA:
            projected[key] = _finite_nonnegative(value, key)
        else:
            if value is None and key == "error_type":
                continue
            projected[key] = _identifier(value, key)
    return projected


def _optional_enum(target: dict[str, Any], key: str, value: str | None, allowed: set[str]) -> None:
    if value is None:
        return
    if value not in allowed:
        raise LangfuseProjectionError(f"{key} is not allowlisted: {value!r}")
    target[key] = value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise LangfuseProjectionError(f"{label} must be a stable identifier")
    _reject_sensitive_value(value, label)
    return value


def _opaque(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value):
        raise LangfuseProjectionError(f"{label} must be an opaque identifier")
    _reject_sensitive_value(value, label)
    return value


def _finite_nonnegative(value: Any, label: str) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
        raise LangfuseProjectionError(f"{label} must be a finite non-negative number")
    return value


def _reject_sensitive_value(value: Any, label: str) -> None:
    if not isinstance(value, str):
        return
    lowered = value.lower()
    if _ABSOLUTE_WINDOWS.match(value) or value.startswith(("/", "\\\\")):
        raise LangfuseProjectionError(f"{label} contains an absolute path")
    if any(marker in lowered for marker in _CREDENTIAL_MARKERS):
        raise LangfuseProjectionError(f"{label} contains credential-like content")
