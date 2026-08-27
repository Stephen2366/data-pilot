"""M48-B/C：有界 Task Context、deterministic Compact 与唯一 Context Builder。

这个 module 把三类容易散落的复杂度藏在一个小 interface 后：

1. 私有 recent user turns 与安全 typed turn facts 的严格持久化；
2. 5-turn / 75% 双触发和 deterministic Task Compact；
3. 各节点最小 Context 的统一投影；
4. M49 最近完成结果的有界 digest，使重启解释无需重跑 Tool/provider。

Compact 是 TaskState/event 的派生索引，不是业务、Evidence 或权限 authority。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from engine.phase4b.b6_contracts import load_b6_contract_bundle
from engine.phase4b.identity import canonical_hash
from engine.phase4b.loop_contracts import AgentNodeContext
from engine.phase4b.task_runtime import TaskDelta, TaskState

_BUNDLE = load_b6_contract_bundle()
_POLICY = _BUNDLE.payload["trigger"]
_FORBIDDEN = frozenset(str(item).casefold() for item in _BUNDLE.payload["forbidden_payload_fields"])

LEGACY_CONTEXT_SCHEMA_VERSION = str(_BUNDLE.payload["context_schema_version"])
LEGACY_COMPACT_SCHEMA_VERSION = str(_BUNDLE.payload["compact_schema_version"])
# M49 additive successor：B6 v1 artifact 保持只读，当前 runtime 写入带有界结果摘要的 v2。
CONTEXT_SCHEMA_VERSION = "phase4b-task-context-window-v2"
COMPACT_SCHEMA_VERSION = "phase4b-task-compact-v2"
RESULT_DIGEST_SCHEMA_VERSION = "phase4b-task-result-digest-v1"
NODE_CONTEXT_VERSION = str(_BUNDLE.payload["node_context_version"])


class TaskContextError(ValueError):
    """Context/Compact 的 closed-world、大小或来源错误。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _json_safe(value: Any, *, path: str = "$") -> Any:
    """递归拒绝敏感 key 和任意对象，避免 context payload 成为隐私旁路。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, path=f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key.casefold() in _FORBIDDEN:
                raise TaskContextError("task_context_schema_incompatible", f"{path} 包含禁止或非字符串 key")
            result[key] = _json_safe(item, path=f"{path}.{key}")
        return result
    raise TaskContextError("task_context_schema_incompatible", f"{path} 包含不可持久化类型")


def _exact(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    """要求对象字段精确闭合，防止新旧 worker 静默误读。"""

    if not isinstance(value, Mapping) or set(value) != keys:
        raise TaskContextError("task_context_schema_incompatible", f"{label} 字段不闭合")
    return value


@dataclass(frozen=True)
class RawUserTurn:
    """只存在 checkpoint context payload 的短期原文；公开投影永不返回 text。"""

    ordinal: int
    version_after: int
    text: str = field(repr=False, compare=True)
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        size = len(self.text.encode("utf-8"))
        if self.ordinal < 1 or self.version_after < 1 or size > int(_POLICY["recent_raw_turn_max_bytes"]):
            raise TaskContextError("task_context_payload_too_large", f"raw turn bytes={size}")
        object.__setattr__(self, "identity", canonical_hash({
            "ordinal": self.ordinal, "version_after": self.version_after, "text": self.text,
        }))

    def safe_projection(self) -> dict[str, Any]:
        """只公开不可逆 identity 与规模，不泄露短期原文。"""

        return {
            "ordinal": self.ordinal, "version_after": self.version_after,
            "identity": self.identity, "byte_count": len(self.text.encode("utf-8")),
        }

    def persisted_projection(self) -> dict[str, Any]:
        """返回仅供 strict codec 落库的私有形状。"""

        return {"ordinal": self.ordinal, "version_after": self.version_after, "text": self.text}


@dataclass(frozen=True)
class TaskResultDigest:
    """最近一次完整回答的有界持久摘要；不保存 SQL、rows、prompt 或文档原文。"""

    route: str
    answer_status: str
    summary_text: str = field(repr=False)
    evidence_ids: tuple[str, ...] = ()
    digest_version: str = RESULT_DIGEST_SCHEMA_VERSION
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        size = len(self.summary_text.encode("utf-8"))
        if (
            self.digest_version != RESULT_DIGEST_SCHEMA_VERSION
            or self.answer_status != "complete"
            or not self.summary_text.strip()
            or size > 8192
            or len(self.evidence_ids) > 16
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
        ):
            raise TaskContextError("task_context_payload_too_large", f"result digest invalid bytes={size}")
        object.__setattr__(self, "identity", canonical_hash(self.safe_projection(include_identity=False)))

    def safe_projection(self, *, include_identity: bool = True) -> dict[str, Any]:
        """返回可落库的有界摘要；这里的 safe 指闭集限额，不代表摘要是业务 Evidence。"""

        result = {
            "digest_version": self.digest_version, "route": self.route,
            "answer_status": self.answer_status, "summary_text": self.summary_text,
            "evidence_ids": list(self.evidence_ids),
        }
        if include_identity:
            result["identity"] = self.identity
        return result


@dataclass(frozen=True)
class TypedTurnFact:
    """event v2/context window 共用的逐 turn 安全事实。"""

    ordinal: int
    version_after: int
    delta_category: str
    transition_identity: str
    state_identity: str
    constraint_keys: tuple[str, ...]
    requirement_identities: tuple[str, ...]
    active_evidence_identities: tuple[str, ...]
    action_count: int
    termination_reason: str | None
    budget_identity: str | None
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        if self.ordinal < 1 or self.version_after < 1 or self.action_count < 0:
            raise TaskContextError("task_context_schema_incompatible", "typed turn ordinal/version/count 非法")
        object.__setattr__(self, "identity", canonical_hash(self.safe_projection(include_identity=False)))

    def safe_projection(self, *, include_identity: bool = True) -> dict[str, Any]:
        """形成 event/context 可共享且不含正文/rows 的 closed-world 投影。"""

        result = {
            "ordinal": self.ordinal, "version_after": self.version_after,
            "delta_category": self.delta_category, "transition_identity": self.transition_identity,
            "state_identity": self.state_identity, "constraint_keys": list(self.constraint_keys),
            "requirement_identities": list(self.requirement_identities),
            "active_evidence_identities": list(self.active_evidence_identities),
            "action_count": self.action_count, "termination_reason": self.termination_reason,
            "budget_identity": self.budget_identity,
        }
        if include_identity:
            result["identity"] = self.identity
        return result


@dataclass(frozen=True)
class TaskCompact:
    """由 TaskState + typed turn facts 唯一派生的可验证 Compact；当前写 v2、兼容读 v1。"""

    goal: str
    constraints: tuple[tuple[str, Any], ...]
    pending_questions: tuple[str, ...]
    requirements: tuple[str, ...]
    evidence: tuple[Mapping[str, Any], ...]
    last_action_attempts: tuple[Mapping[str, Any], ...]
    last_budget: Mapping[str, Any] | None
    last_termination: Mapping[str, Any] | None
    result_digest: TaskResultDigest | None
    high_risk_references: Mapping[str, Any]
    source_turn_range: tuple[int, int]
    source_version_range: tuple[int, int]
    source_identities: tuple[str, ...]
    source_watermark: int
    trigger: str
    compact_version: str = COMPACT_SCHEMA_VERSION
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            self.compact_version not in {LEGACY_COMPACT_SCHEMA_VERSION, COMPACT_SCHEMA_VERSION}
            or self.source_turn_range[0] > self.source_turn_range[1]
            or self.source_version_range[0] > self.source_version_range[1]
            or self.source_turn_range[1] != self.source_watermark
        ):
            raise TaskContextError("task_context_schema_incompatible", "Compact version/source range 非法")
        if set(self.high_risk_references) != {
            "goal_exact", "constraints_exact", "evidence_refs_exact",
        }:
            raise TaskContextError("task_context_schema_incompatible", "Compact 高风险 reference 不闭合")
        if (
            self.high_risk_references["goal_exact"] != self.goal
            or self.high_risk_references["constraints_exact"] != dict(self.constraints)
        ):
            raise TaskContextError("task_evidence_revalidation_failed", "Compact 高风险事实与 typed 字段不一致")
        object.__setattr__(self, "identity", canonical_hash(self.safe_projection(include_identity=False)))

    def safe_projection(self, *, include_identity: bool = True) -> dict[str, Any]:
        """Compact 本身只含 typed/安全事实，可供 codec 与 builder 共用。"""

        result = {
            "compact_version": self.compact_version, "goal": self.goal,
            "constraints": dict(self.constraints), "pending_questions": list(self.pending_questions),
            "requirements": list(self.requirements), "evidence": [dict(item) for item in self.evidence],
            "last_action_attempts": [dict(item) for item in self.last_action_attempts],
            "last_budget": dict(self.last_budget) if self.last_budget is not None else None,
            "last_termination": dict(self.last_termination) if self.last_termination is not None else None,
            "high_risk_references": dict(self.high_risk_references),
            "source_turn_range": list(self.source_turn_range),
            "source_version_range": list(self.source_version_range),
            "source_identities": list(self.source_identities),
            "source_watermark": self.source_watermark, "trigger": self.trigger,
        }
        if self.compact_version == COMPACT_SCHEMA_VERSION:
            result["result_digest"] = self.result_digest.safe_projection() if self.result_digest else None
        if include_identity:
            result["identity"] = self.identity
        return result


@dataclass(frozen=True)
class TaskContextWindow:
    """一个 task 当前唯一的 bounded context material。"""

    compact: TaskCompact | None = None
    uncovered_turns: tuple[TypedTurnFact, ...] = ()
    recent_raw_turns: tuple[RawUserTurn, ...] = ()
    committed_turns_since_compact: int = 0
    source_watermark: int = 0
    source_complete: bool = True
    latest_result_digest: TaskResultDigest | None = None
    context_version: str = CONTEXT_SCHEMA_VERSION
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        if self.context_version not in {LEGACY_CONTEXT_SCHEMA_VERSION, CONTEXT_SCHEMA_VERSION}:
            raise TaskContextError("task_context_schema_incompatible", self.context_version)
        if self.context_version == LEGACY_CONTEXT_SCHEMA_VERSION and self.latest_result_digest is not None:
            raise TaskContextError("task_context_schema_incompatible", "legacy context 不能携带 result digest")
        if self.committed_turns_since_compact != len(self.uncovered_turns):
            raise TaskContextError("task_context_schema_incompatible", "uncovered turn 计数不一致")
        if len(self.recent_raw_turns) > int(_POLICY["recent_raw_turn_count"]):
            raise TaskContextError("task_context_payload_too_large", "recent raw turn 数量超限")
        ordinals = [item.ordinal for item in self.uncovered_turns]
        previous_watermark = self.compact.source_watermark if self.compact else 0
        expected_ordinals = list(range(previous_watermark + 1, self.source_watermark + 1))
        versions = [item.version_after for item in self.uncovered_turns]
        if ordinals != expected_ordinals or versions != sorted(set(versions)):
            raise TaskContextError("task_context_schema_incompatible", "turn ordinal/watermark 不闭合")
        recent_ordinals = [item.ordinal for item in self.recent_raw_turns]
        if (
            recent_ordinals != sorted(set(recent_ordinals))
            or any(ordinal > self.source_watermark for ordinal in recent_ordinals)
        ):
            raise TaskContextError("task_context_schema_incompatible", "recent raw turn lineage 不闭合")
        object.__setattr__(self, "identity", canonical_hash(self.persisted_projection(include_identity=False)))

    @classmethod
    def empty(cls) -> "TaskContextWindow":
        """为 start/legacy-null checkpoint 提供唯一空形状。"""

        return cls()

    @classmethod
    def legacy_incomplete(cls) -> "TaskContextWindow":
        """表示 0005 前 active checkpoint：可续用，但达到 trigger 时禁止猜历史。"""

        return cls(source_complete=False)

    def persisted_projection(self, *, include_identity: bool = True) -> dict[str, Any]:
        """codec 使用的完整形状；其中 recent raw 不得进入公开投影。"""

        result = {
            "context_version": self.context_version,
            "compact": self.compact.safe_projection() if self.compact else None,
            "uncovered_turns": [item.safe_projection() for item in self.uncovered_turns],
            "recent_raw_turns": [item.persisted_projection() for item in self.recent_raw_turns],
            "committed_turns_since_compact": self.committed_turns_since_compact,
            "source_watermark": self.source_watermark, "source_complete": self.source_complete,
        }
        if self.context_version == CONTEXT_SCHEMA_VERSION:
            result["latest_result_digest"] = (
                self.latest_result_digest.safe_projection() if self.latest_result_digest else None
            )
        if include_identity:
            result["identity"] = self.identity
        return result

    def safe_projection(self) -> dict[str, Any]:
        """API/Trace 只看到身份、范围、数量和 trigger，不看到 raw/完整 Compact。"""

        return {
            "context_version": self.context_version, "context_identity": self.identity,
            "compact_identity": self.compact.identity if self.compact else None,
            "compact_trigger": self.compact.trigger if self.compact else None,
            "compact_source_turn_range": list(self.compact.source_turn_range) if self.compact else None,
            "source_watermark": self.source_watermark,
            "source_complete": self.source_complete,
            "uncovered_turn_count": len(self.uncovered_turns),
            "recent_raw_turn_count": len(self.recent_raw_turns),
            "result_digest_identity": self.latest_result_digest.identity if self.latest_result_digest else None,
        }


@dataclass(frozen=True)
class CompactDecision:
    """一次 accepted turn 的 trigger/fallback 安全事实。"""

    outcome: str
    reason_code: str
    trigger: str | None
    context_identity_before: str
    context_identity_after: str
    compact_identity: str | None
    candidate_budget_ratio: float

    def safe_projection(self) -> dict[str, Any]:
        return dict(self.__dict__)


class TaskContextCodec:
    """TaskContextWindow 的严格、可逆、大小受限 codec。"""

    schema_version = CONTEXT_SCHEMA_VERSION

    def __init__(self, *, max_bytes: int = 65536) -> None:
        self.max_bytes = max_bytes

    def encode(self, window: TaskContextWindow) -> dict[str, Any]:
        """执行敏感 key、闭集和 UTF-8 大小门。"""

        payload = _json_safe(window.persisted_projection())
        size = len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if size > self.max_bytes:
            raise TaskContextError("task_context_payload_too_large", f"{size}>{self.max_bytes}")
        return payload

    def decode(self, payload: Any) -> TaskContextWindow:
        """严格恢复 window，并通过 encode 比较捕捉静默类型漂移。"""

        safe_payload = _json_safe(payload)
        version = safe_payload.get("context_version") if isinstance(safe_payload, Mapping) else None
        keys = {
            "context_version", "compact", "uncovered_turns", "recent_raw_turns",
            "committed_turns_since_compact", "source_watermark", "source_complete", "identity",
        }
        if version == CONTEXT_SCHEMA_VERSION:
            keys.add("latest_result_digest")
        elif version != LEGACY_CONTEXT_SCHEMA_VERSION:
            raise TaskContextError("task_context_schema_incompatible", str(version))
        raw = _exact(safe_payload, keys, "TaskContextWindow")
        compact = self._decode_compact(raw["compact"]) if raw["compact"] is not None else None
        digest = (
            self._decode_result_digest(raw["latest_result_digest"])
            if version == CONTEXT_SCHEMA_VERSION and raw["latest_result_digest"] is not None
            else None
        )
        turns = tuple(self._decode_turn(item) for item in raw["uncovered_turns"])
        recent = tuple(
            RawUserTurn(**_exact(item, {"ordinal", "version_after", "text"}, "RawUserTurn"))
            for item in raw["recent_raw_turns"]
        )
        window = TaskContextWindow(
            compact=compact, uncovered_turns=turns, recent_raw_turns=recent,
            committed_turns_since_compact=int(raw["committed_turns_since_compact"]),
            source_watermark=int(raw["source_watermark"]), source_complete=bool(raw["source_complete"]),
            latest_result_digest=digest, context_version=str(raw["context_version"]),
        )
        if window.identity != raw["identity"] or self.encode(window) != raw:
            raise TaskContextError("task_compact_identity_mismatch", "context decode 后 identity/round-trip 不一致")
        return window

    @staticmethod
    def _decode_turn(value: Any) -> TypedTurnFact:
        """恢复并复核一条 typed turn；外层 hash 正确也不能掩盖内层篡改。"""

        row = _exact(value, {
            "ordinal", "version_after", "delta_category", "transition_identity", "state_identity",
            "constraint_keys", "requirement_identities", "active_evidence_identities", "action_count",
            "termination_reason", "budget_identity", "identity",
        }, "TypedTurnFact")
        turn = TypedTurnFact(
            ordinal=int(row["ordinal"]), version_after=int(row["version_after"]),
            delta_category=str(row["delta_category"]), transition_identity=str(row["transition_identity"]),
            state_identity=str(row["state_identity"]), constraint_keys=tuple(row["constraint_keys"]),
            requirement_identities=tuple(row["requirement_identities"]),
            active_evidence_identities=tuple(row["active_evidence_identities"]),
            action_count=int(row["action_count"]), termination_reason=row["termination_reason"],
            budget_identity=row["budget_identity"],
        )
        if turn.identity != row["identity"]:
            raise TaskContextError("task_compact_identity_mismatch", "typed turn identity 漂移")
        return turn

    @staticmethod
    def _decode_compact(value: Any) -> TaskCompact:
        """按版本闭集解码 Compact，v1 无 digest、v2 必须显式携带 digest 槽位。"""

        if not isinstance(value, Mapping):
            raise TaskContextError("task_context_schema_incompatible", "TaskCompact 必须为 object")
        version = value.get("compact_version")
        keys = {
            "compact_version", "goal", "constraints", "pending_questions", "requirements", "evidence",
            "last_action_attempts", "last_budget", "last_termination", "high_risk_references",
            "source_turn_range", "source_version_range", "source_identities", "source_watermark",
            "trigger", "identity",
        }
        if version == COMPACT_SCHEMA_VERSION:
            keys.add("result_digest")
        elif version != LEGACY_COMPACT_SCHEMA_VERSION:
            raise TaskContextError("task_context_schema_incompatible", str(version))
        row = _exact(value, keys, "TaskCompact")
        digest = (
            TaskContextCodec._decode_result_digest(row["result_digest"])
            if version == COMPACT_SCHEMA_VERSION and row["result_digest"] is not None
            else None
        )
        compact = TaskCompact(
            goal=str(row["goal"]), constraints=tuple(dict(row["constraints"]).items()),
            pending_questions=tuple(row["pending_questions"]), requirements=tuple(row["requirements"]),
            evidence=tuple(dict(item) for item in row["evidence"]),
            last_action_attempts=tuple(dict(item) for item in row["last_action_attempts"]),
            last_budget=dict(row["last_budget"]) if row["last_budget"] is not None else None,
            last_termination=dict(row["last_termination"]) if row["last_termination"] is not None else None,
            result_digest=digest,
            high_risk_references=dict(row["high_risk_references"]),
            source_turn_range=tuple(row["source_turn_range"]), source_version_range=tuple(row["source_version_range"]),
            source_identities=tuple(row["source_identities"]), source_watermark=int(row["source_watermark"]),
            trigger=str(row["trigger"]), compact_version=str(row["compact_version"]),
        )
        if compact.identity != row["identity"]:
            raise TaskContextError("task_compact_identity_mismatch", "Compact identity 漂移")
        return compact

    @staticmethod
    def _decode_result_digest(value: Any) -> TaskResultDigest:
        """恢复 bounded digest，并重新计算 identity 防止摘要或 Evidence ID 被替换。"""

        row = _exact(value, {
            "digest_version", "route", "answer_status", "summary_text", "evidence_ids", "identity",
        }, "TaskResultDigest")
        digest = TaskResultDigest(
            route=str(row["route"]), answer_status=str(row["answer_status"]),
            summary_text=str(row["summary_text"]), evidence_ids=tuple(row["evidence_ids"]),
            digest_version=str(row["digest_version"]),
        )
        if digest.identity != row["identity"]:
            raise TaskContextError("task_compact_identity_mismatch", "result digest identity 漂移")
        return digest


class TaskContextBuilder:
    """触发、Compact、turn append 与 node projection 的唯一深 interface。"""

    def __init__(self, *, committed_turns: int = 5, candidate_budget_ratio: float = 0.75) -> None:
        if committed_turns < 1 or not 0 < candidate_budget_ratio < 1:
            raise ValueError("task_context_policy_invalid")
        self.committed_turns = committed_turns
        self.candidate_budget_ratio = candidate_budget_ratio
        self.identity = canonical_hash({
            "runtime": _BUNDLE.payload["runtime_identity"], "committed_turns": committed_turns,
            "candidate_budget_ratio": candidate_budget_ratio,
            "recent_raw_turn_count": _POLICY["recent_raw_turn_count"],
            "recent_raw_turn_max_bytes": _POLICY["recent_raw_turn_max_bytes"],
        })

    def prepare(
        self,
        *,
        window: TaskContextWindow | None,
        state: TaskState,
        candidate_contexts: Sequence[AgentNodeContext],
    ) -> tuple[TaskContextWindow, CompactDecision]:
        """在深节点执行前判断 dual trigger，并确定性生成 Compact。"""

        current = window or TaskContextWindow.empty()
        ratio = max((item.estimated_tokens / item.token_budget for item in candidate_contexts), default=0.0)
        trigger = None
        if current.committed_turns_since_compact >= self.committed_turns:
            trigger = "committed_turns"
        elif ratio >= self.candidate_budget_ratio:
            trigger = "candidate_node_budget"
        if trigger is None:
            decision = CompactDecision(
                "not_triggered", "task_compact_not_triggered", None,
                current.identity, current.identity, current.compact.identity if current.compact else None, ratio,
            )
            return current, decision
        if not current.source_complete or not current.uncovered_turns:
            # legacy v1 event/checkpoint 没有可核对 source 时禁止猜测补齐。
            raise TaskContextError("task_compact_source_incomplete", "trigger 命中但没有 typed turn source")
        try:
            compact = self._build_compact(state=state, window=current, trigger=trigger)
        except TaskContextError:
            # 构建候选失败时，只有“原 source 仍能被 strict codec 安全保存”才允许继续。
            # 这不是吞错：decision 明确记录 fallback，且不删任何 typed/raw source；若原窗口
            # 自身也超限/不闭合，codec 会再次抛错并由 task turn 在 Tool 前失败关闭。
            TaskContextCodec().encode(current)
            return current, CompactDecision(
                "fallback_uncompacted", "task_compact_fallback_uncompacted", trigger,
                current.identity, current.identity,
                current.compact.identity if current.compact else None, ratio,
            )
        prepared = TaskContextWindow(
            compact=compact, uncovered_turns=(), recent_raw_turns=current.recent_raw_turns,
            committed_turns_since_compact=0, source_watermark=current.source_watermark,
            source_complete=current.source_complete, latest_result_digest=current.latest_result_digest,
            context_version=CONTEXT_SCHEMA_VERSION,
        )
        return prepared, CompactDecision(
            "triggered_and_committed", "task_compact_committed", trigger,
            current.identity, prepared.identity, compact.identity, ratio,
        )

    def append_committed_turn(
        self,
        *,
        window: TaskContextWindow,
        question: str,
        version_after: int,
        delta: TaskDelta,
        state: TaskState,
        action_count: int,
        termination_reason: str | None,
        budget_identity: str | None,
        result_digest: TaskResultDigest | None = None,
    ) -> TaskContextWindow:
        """commit 前追加本 turn；调用方把返回值与 state/event 一起原子提交。"""

        ordinal = window.source_watermark + 1
        active_evidence = tuple(
            canonical_hash(item.safe_projection()) for item in state.evidence if item.validity == "active"
        )
        turn = TypedTurnFact(
            ordinal=ordinal, version_after=version_after, delta_category=delta.category,
            transition_identity=state.identity, state_identity=state.identity,
            constraint_keys=tuple(key for key, _ in state.constraints),
            requirement_identities=tuple(state.requirements),
            active_evidence_identities=active_evidence, action_count=action_count,
            termination_reason=termination_reason, budget_identity=budget_identity,
        )
        raw = RawUserTurn(ordinal=ordinal, version_after=version_after, text=question)
        recent = (*window.recent_raw_turns, raw)[-int(_POLICY["recent_raw_turn_count"]):]
        return TaskContextWindow(
            compact=window.compact, uncovered_turns=(*window.uncovered_turns, turn),
            recent_raw_turns=tuple(recent),
            committed_turns_since_compact=window.committed_turns_since_compact + 1,
            source_watermark=ordinal, source_complete=window.source_complete,
            latest_result_digest=result_digest or window.latest_result_digest,
            context_version=CONTEXT_SCHEMA_VERSION,
        )

    def project_node_contexts(
        self,
        *,
        question: str,
        state: TaskState,
        delta: TaskDelta,
        prior_state_identity: str | None,
        window: TaskContextWindow,
    ) -> tuple[AgentNodeContext, ...]:
        """按目的构建最小实际输入；raw 字段只允许 Turn Understanding 看见。"""

        context_ref = window.safe_projection()
        compact_ref = window.compact.identity if window.compact else None
        sources = tuple(filter(None, (state.identity, window.identity, compact_ref)))
        turn_payload = {
            "question": question,
            "recent_user_turns": [item.text for item in window.recent_raw_turns],
            "prior_state_identity": prior_state_identity,
            "task_context": context_ref,
        }
        route_payload = {
            "goal": state.goal, "constraints": dict(state.constraints),
            "requirements": list(state.requirements), "route": state.route,
            "task_context": context_ref,
        }
        sql_payload = {
            "metric": dict(state.constraints).get("metric"),
            "periods": list(dict(state.constraints).get("periods", ())),
            "requirement": state.requirements[-1] if state.requirements else None,
            "task_context": context_ref,
        }
        controller_payload = {
            "status": state.status, "route": state.route,
            "pending_questions": list(state.pending_questions),
            "active_evidence_refs": [item.ref for item in state.evidence if item.validity == "active"],
            "task_context": context_ref,
        }
        return (
            AgentNodeContext(
                "turn_understanding", (delta.source_identity, *sources), turn_payload,
                tuple(turn_payload), 4, 1024, context_version=NODE_CONTEXT_VERSION,
                private_fields=("question", "recent_user_turns"),
            ),
            AgentNodeContext("route_execution", sources, route_payload, tuple(route_payload), 5, 1024, context_version=NODE_CONTEXT_VERSION),
            AgentNodeContext("sql", sources, sql_payload, tuple(sql_payload), 4, 768, context_version=NODE_CONTEXT_VERSION),
            AgentNodeContext("controller_response", sources, controller_payload, tuple(controller_payload), 5, 1024, context_version=NODE_CONTEXT_VERSION),
        )

    @staticmethod
    def _build_compact(*, state: TaskState, window: TaskContextWindow, trigger: str) -> TaskCompact:
        """从 exact typed values 构建 Compact；不做自然语言释义或模糊归并。"""

        turns = window.uncovered_turns
        start_turn = turns[0].ordinal if turns else 1
        start_version = turns[0].version_after if turns else 1
        evidence = tuple(item.safe_projection() for item in state.evidence)
        # ★ 金额、时间、指标、否定与政策例外必须保留原 typed 值；这里直接复制而非总结。
        high_risk = {
            "goal_exact": state.goal,
            "constraints_exact": dict(state.constraints),
            "evidence_refs_exact": [dict(item.ref) for item in state.evidence],
        }
        sources = tuple(dict.fromkeys((
            *((window.compact.identity,) if window.compact else ()),
            *(item.identity for item in turns), state.identity,
        )))
        return TaskCompact(
            goal=state.goal, constraints=state.constraints, pending_questions=state.pending_questions,
            requirements=state.requirements, evidence=evidence,
            last_action_attempts=state.last_action_attempts, last_budget=state.last_budget,
            last_termination=state.last_termination, high_risk_references=high_risk,
            result_digest=window.latest_result_digest,
            source_turn_range=(start_turn, window.source_watermark),
            source_version_range=(start_version, turns[-1].version_after),
            source_identities=sources, source_watermark=window.source_watermark, trigger=trigger,
        )


def context_estimate(contexts: Iterable[AgentNodeContext]) -> dict[str, float]:
    """诊断 helper：只返回每个 purpose 的预算比例，不返回 payload。"""

    return {item.purpose: item.estimated_tokens / item.token_budget for item in contexts}
