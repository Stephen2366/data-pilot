"""M47-B：TaskState v2 的严格、可逆、大小受限持久化 codec。"""

from __future__ import annotations

import json
from dataclasses import fields
from typing import Any, Mapping

from engine.phase4b.b5_contracts import load_b5_contract_bundle
from engine.phase4b.loop_contracts import EvidenceRequirement
from engine.phase4b.task_runtime import TASK_STATE_VERSION, TaskEvidence, TaskState

_BUNDLE = load_b5_contract_bundle()
_FORBIDDEN = frozenset(str(item).lower() for item in _BUNDLE.payload["forbidden_payload_fields"])
_STATE_KEYS = frozenset(field.name for field in fields(TaskState))
_REQUIREMENT_KEYS = frozenset(field.name for field in fields(EvidenceRequirement))
_EVIDENCE_KEYS = frozenset(field.name for field in fields(TaskEvidence))


class TaskStateCodecError(ValueError):
    """持久化 payload 不闭合、不安全或无法无损恢复。"""

    def __init__(self, reason_code: str, message: str) -> None:
        """保留可由 boundary 映射的稳定 codec reason。"""

        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _ensure_json_safe(value: Any, *, path: str = "$") -> Any:
    """拒绝任意对象与敏感字段名，只允许 JSON closed-world 值。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_ensure_json_safe(item, path=f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TaskStateCodecError("task_schema_incompatible", f"{path} 包含非字符串 key")
            if key.lower() in _FORBIDDEN:
                raise TaskStateCodecError("task_schema_incompatible", f"{path}.{key} 为禁止字段")
            result[key] = _ensure_json_safe(item, path=f"{path}.{key}")
        return result
    raise TaskStateCodecError("task_schema_incompatible", f"{path} 包含不可持久化类型")


def _expect_keys(value: Any, expected: frozenset[str], label: str) -> Mapping[str, Any]:
    """拒绝缺字段与未知字段，防止 schema 漂移被宽松吞掉。"""

    if not isinstance(value, Mapping) or set(value) != expected:
        raise TaskStateCodecError("task_schema_incompatible", f"{label} 字段不闭合")
    return value


class TaskStateCodec:
    """把内存 dataclass 与数据库 JSON 往返；不借用对外脱敏投影。"""

    schema_version = TASK_STATE_VERSION

    def __init__(self, *, max_bytes: int = 65536) -> None:
        """冻结单个 checkpoint payload 的 UTF-8 字节上限。"""

        self.max_bytes = max_bytes

    def encode(self, state: TaskState) -> dict[str, Any]:
        """把 TaskState 转成唯一可持久 JSON 形状并执行隐私/大小门。"""

        if state.state_version != self.schema_version:
            raise TaskStateCodecError("task_schema_incompatible", state.state_version)
        payload = {
            "owner_ref": state.owner_ref,
            "generation": state.generation,
            "status": state.status,
            "goal": state.goal,
            "constraints": dict(state.constraints),
            "pending_questions": list(state.pending_questions),
            "requirements": list(state.requirements),
            "evidence_requirements": [
                {
                    "identity": item.identity, "kind": item.kind, "purpose": item.purpose,
                    "query": item.query, "runtime_scope": item.runtime_scope,
                    "expected_document_keys": list(item.expected_document_keys),
                    "depends_on": item.depends_on, "required": item.required,
                    "freshness": item.freshness,
                }
                for item in state.evidence_requirements
            ],
            "route": state.route,
            "evidence": [
                {
                    "ref": dict(item.ref), "route": item.route,
                    "requirement_identity": item.requirement_identity, "validity": item.validity,
                    "invalidation_reason": item.invalidation_reason,
                    "source_generation": item.source_generation, "action_id": item.action_id,
                    "input_fingerprint": item.input_fingerprint,
                    "runtime_identity": item.runtime_identity,
                }
                for item in state.evidence
            ],
            "termination": state.termination,
            "last_action_attempts": [dict(item) for item in state.last_action_attempts],
            "last_budget": dict(state.last_budget) if state.last_budget is not None else None,
            "last_termination": dict(state.last_termination) if state.last_termination is not None else None,
            "state_version": state.state_version,
        }
        safe = _ensure_json_safe(payload)
        size = len(json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if size > self.max_bytes:
            raise TaskStateCodecError("task_payload_too_large", f"{size}>{self.max_bytes}")
        return safe

    def decode(self, payload: Any) -> TaskState:
        """严格恢复 TaskState，并用再次编码证明无静默类型漂移。"""

        raw = _expect_keys(_ensure_json_safe(payload), _STATE_KEYS, "TaskState")
        if raw["state_version"] != self.schema_version:
            raise TaskStateCodecError("task_schema_incompatible", str(raw["state_version"]))
        requirements = []
        for item in raw["evidence_requirements"]:
            row = _expect_keys(item, _REQUIREMENT_KEYS, "EvidenceRequirement")
            requirements.append(EvidenceRequirement(**{**row, "expected_document_keys": tuple(row["expected_document_keys"])}))
        evidence = []
        for item in raw["evidence"]:
            row = _expect_keys(item, _EVIDENCE_KEYS, "TaskEvidence")
            evidence.append(TaskEvidence(**row))
        try:
            state = TaskState(
                owner_ref=str(raw["owner_ref"]), generation=int(raw["generation"]), status=raw["status"],
                goal=str(raw["goal"]), constraints=tuple(dict(raw["constraints"]).items()),
                pending_questions=tuple(raw["pending_questions"]), requirements=tuple(raw["requirements"]),
                evidence_requirements=tuple(requirements), route=raw["route"], evidence=tuple(evidence),
                termination=raw["termination"], last_action_attempts=tuple(dict(item) for item in raw["last_action_attempts"]),
                last_budget=dict(raw["last_budget"]) if raw["last_budget"] is not None else None,
                last_termination=dict(raw["last_termination"]) if raw["last_termination"] is not None else None,
                state_version=str(raw["state_version"]),
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise TaskStateCodecError("task_schema_incompatible", str(exc)) from exc
        # ★ encode 再比较，捕获 bool→int 等 Python 宽松转换造成的静默漂移。
        if self.encode(state) != raw:
            raise TaskStateCodecError("task_schema_incompatible", "decode 后无法严格 round-trip")
        return state
