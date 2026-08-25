"""M45 B3：隔离的 RAG recovery diagnostic 深模块。

★ 本模块只证明“某个 Observation 是否应准入某个 recovery action，以及动作是否新增
Evidence”。它刻意不接 M44 产品 Loop，也不生成最终答案；M46 才能消费已通过的 action
card。调用方只需要提供一个现有 Knowledge Tool 和（external 时）一个 expansion adapter，
ACL、预算、去重、停止和安全投影都留在这个 interface 后面。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from time import perf_counter
from typing import Any, Literal, Protocol

from engine.governance import TrustedCaller
from engine.phase4b.identity import canonical_hash
from engine.phase4b.loop_contracts import EvidenceDelta, ProgressDecision, ResourceConsumption
from engine.rag.evidence import DocumentEvidencePayload, Evidence, EvidenceLedger
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool, RetrievalOutcome
from engine.rag.retrieval import RetrievalBudget

RecoveryActionId = Literal["query_rewrite_candidate", "context_expansion_candidate", "stop"]
TriState = Literal["passed", "failed", "not_observed"]
RequirementValueShape = Literal["none", "numeric", "duration", "schedule", "ordered_steps"]
RequirementMarkerMatch = Literal["exact", "token_overlap"]
ContinuationPolicy = Literal["disabled", "procedure_boundary_v1"]
FunnelStage = Literal["retrieved", "selected", "generation_visible", "support", "cited", "answer"]
FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    "retrieved", "selected", "generation_visible", "support", "cited", "answer"
)


class RAGDiagnosticContractError(ValueError):
    """closed-world 诊断合同失败；reason_code 可稳定进入测试和 triage。"""

    def __init__(self, reason_code: str, message: str = "") -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}" if message else reason_code)


@dataclass(frozen=True)
class RequirementSlot:
    """检索前由服务端冻结的一个语义要求，不包含 gold 文档身份。

    ``support_marker_groups`` 是保守、确定性的支持判据：每组至少命中一个 marker，全部组
    都命中才算当前 Evidence 支持该 slot。它类似 SQL 里的 typed predicate，不是事后拿 gold
    标题反推 query。完整 marker 只留在私有 runtime；安全投影仅保存 hash。
    """

    identity: str
    focused_query: str
    support_marker_groups: tuple[tuple[str, ...], ...]
    value_shape: RequirementValueShape = "none"
    marker_match_mode: RequirementMarkerMatch = "exact"
    signature: str = field(init=False)

    def __post_init__(self) -> None:
        """规范化 marker 并生成向后兼容的 content-bound slot signature。"""

        if (
            not self.identity.strip()
            or not self.focused_query.strip()
            or not self.support_marker_groups
            or self.value_shape not in {"none", "numeric", "duration", "schedule", "ordered_steps"}
            or self.marker_match_mode not in {"exact", "token_overlap"}
        ):
            raise RAGDiagnosticContractError("requirement_slot_invalid")
        normalized_groups: list[tuple[str, ...]] = []
        for group in self.support_marker_groups:
            normalized = tuple(dict.fromkeys(item.strip().casefold() for item in group if item.strip()))
            if not normalized:
                raise RAGDiagnosticContractError("requirement_slot_invalid")
            normalized_groups.append(normalized)
        object.__setattr__(self, "support_marker_groups", tuple(normalized_groups))
        signature_payload: dict[str, Any] = {
            "identity": self.identity,
            "focused_query": self.focused_query,
            "support_marker_groups": normalized_groups,
        }
        # 旧 deterministic slot 的 identity 必须保持不变；只有重开切片显式使用的新 shape
        # 才进入签名，避免把 P1～P3 不可变 lineage 静默改签。
        if self.value_shape != "none":
            signature_payload["value_shape"] = self.value_shape
        if self.marker_match_mode != "exact":
            signature_payload["marker_match_mode"] = self.marker_match_mode
        object.__setattr__(self, "signature", canonical_hash(signature_payload))

    def supported_by(self, evidence: tuple[Evidence, ...]) -> bool:
        """只读当前已授权 Document Evidence 正文，判断 slot 是否已经覆盖。"""

        if self.marker_match_mode == "token_overlap":
            # ★ proposal slot 不允许从互不相关的多个文档“拼词”：例如 A 文档有 weekly、B 文档
            # 有 afternoon，不能合成一条 schedule Evidence。sibling adapter 对同一 physical doc
            # 的 seed+candidate 联合支持仍显式调用 ``supported_by_text``。
            return any(
                self.supported_by_text(item.payload.content)
                for item in evidence
                if isinstance(item.payload, DocumentEvidencePayload)
            )
        text = "\n".join(
            item.payload.content.casefold()
            for item in evidence
            if isinstance(item.payload, DocumentEvidencePayload)
        )
        return self.supported_by_text(text)

    def supported_by_text(self, text: str) -> bool:
        """marker coverage 外再执行由 signed query 类型推导的通用 value-shape 检查。

        例如“cost rate”不能只看到 ``rate`` 这个词就算支持，还必须出现货币数值。这里不写
        具体答案值；规则由已签名的 identity/focused query 推导，可跨 Scenario 复用。
        """

        normalized = text.casefold()
        if not self.markers_supported_by_text(normalized):
            return False
        query_tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]+", self.focused_query.casefold()))
        if self.identity.endswith("_rate") or "rate" in query_tokens:
            return bool(re.search(r"(?:[$€£]\s*\d|\b(?:usd|eur|gbp)\s*\d)", normalized))
        if self.value_shape == "numeric":
            return bool(re.search(r"\b\d+(?:\.\d+)?%?\b", normalized))
        if self.value_shape == "duration":
            return bool(re.search(
                r"\b\d+(?:\.\d+)?\s*(?:minutes?|hours?|days?|weeks?|mins?|hrs?)\b",
                normalized,
            ))
        if self.value_shape == "schedule":
            has_day = bool(re.search(
                r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                r"mon|tue|wed|thu|fri|sat|sun|daily|weekly)\b",
                normalized,
            ))
            has_time = bool(re.search(
                r"\b(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|morning|afternoon|evening|"
                r"before\s+(?:lunch|noon|close)|after\s+(?:lunch|noon|close))\b",
                normalized,
            ))
            return has_day and has_time
        if self.value_shape == "ordered_steps":
            step_lines = re.findall(
                r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:step\s*)?\d+\s*[).:-]",
                normalized,
            )
            return len(step_lines) >= 2
        return True

    def markers_supported_by_text(self, text: str) -> bool:
        """只判断 marker 语义，不混入 value-shape；proposal seed ranking 可安全复用。"""

        normalized = text.casefold()

        def marker_present(marker: str) -> bool:
            if marker in normalized:
                return True
            if self.marker_match_mode != "token_overlap":
                return False
            tokens = tuple(dict.fromkeys(re.findall(r"[a-z0-9][a-z0-9_-]+", marker)))
            if len(tokens) <= 1:
                return False
            matched = sum(token in normalized for token in tokens)
            required = len(tokens) if len(tokens) == 2 else max(2, (len(tokens) * 2 + 2) // 3)
            return matched >= required

        return bool(normalized) and all(
            any(marker_present(marker) for marker in group) for group in self.support_marker_groups
        )

    def safe_projection(self) -> dict[str, Any]:
        """不保存 focused query 或 marker 明文，避免仓库 artifact 反推题面。"""

        projection = {
            "identity": self.identity,
            "signature": self.signature,
            "focused_query_fingerprint": canonical_hash(self.focused_query),
            "support_group_count": len(self.support_marker_groups),
        }
        if self.value_shape != "none":
            projection["value_shape"] = self.value_shape
        if self.marker_match_mode != "exact":
            projection["marker_match_mode"] = self.marker_match_mode
        return projection


@dataclass(frozen=True)
class RecoveryBudget:
    """M45 child budget；与 M44 production parent budget 完全分账。"""

    max_actions: int = 1
    max_retrieval_batches: int = 2
    max_candidates_per_batch: int = 5
    max_added_evidence: int = 3
    max_expansion_seeds: int = 2
    max_sibling_units_scanned_per_seed: int = 8
    max_added_expansion_evidence: int = 4

    def __post_init__(self) -> None:
        """把 M45 child budget 限定在 plan 冻结的 closed-world 数值。"""

        if self.max_actions != 1 or not (1 <= self.max_retrieval_batches <= 2):
            raise RAGDiagnosticContractError("recovery_budget_invalid")
        if self.max_candidates_per_batch != 5 or self.max_added_evidence != 3:
            raise RAGDiagnosticContractError("recovery_budget_invalid")
        if (
            self.max_expansion_seeds != 2
            or self.max_sibling_units_scanned_per_seed != 8
            or self.max_added_expansion_evidence != 4
        ):
            raise RAGDiagnosticContractError("recovery_budget_invalid")

    def safe_projection(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class FunnelView:
    """同一次 execution 的六层三态视图与唯一首失败层。"""

    stages: tuple[tuple[FunnelStage, TriState], ...]
    first_failure_layer: FunnelStage | None

    def safe_projection(self) -> dict[str, Any]:
        return {"stages": dict(self.stages), "first_failure_layer": self.first_failure_layer}


def project_failure_funnel(observed: dict[FunnelStage, bool | None]) -> FunnelView:
    """把稀疏观测投影为漏斗；上游失败/不可观察时，下游一律 ``not_observed``。"""

    unknown = set(observed) - set(FUNNEL_STAGES)
    if unknown:
        raise RAGDiagnosticContractError("funnel_stage_unknown", ",".join(sorted(unknown)))
    projected: list[tuple[FunnelStage, TriState]] = []
    first_failure: FunnelStage | None = None
    upstream_closed = False
    for stage in FUNNEL_STAGES:
        value = observed.get(stage)
        if upstream_closed or value is None:
            status: TriState = "not_observed"
            upstream_closed = True
        elif value:
            status = "passed"
        else:
            status = "failed"
            first_failure = first_failure or stage
            upstream_closed = True
        projected.append((stage, status))
    return FunnelView(tuple(projected), first_failure)


@dataclass(frozen=True)
class ExpansionPreview:
    """已通过 pre-selection 的相邻 context 候选；只在同进程私有 runtime 流转。"""

    seed_evidence_id: str
    slot_identities: tuple[str, ...]
    opaque_candidates: tuple[Any, ...]


class ContextExpansionAdapter(Protocol):
    """external SQLite authority 在 diagnostic seam 上的最小 adapter interface。"""

    identity: str

    def preview(
        self,
        *,
        seeds: tuple[Evidence, ...],
        unsupported_slots: tuple[RequirementSlot, ...],
        caller: TrustedCaller,
        purpose: str,
        max_seeds: int,
        max_sibling_units_scanned_per_seed: int,
        max_added: int,
    ) -> tuple[ExpansionPreview, ...]: ...

    def materialize(
        self,
        *,
        previews: tuple[ExpansionPreview, ...],
        caller: TrustedCaller,
        purpose: str,
        run_id: str,
        max_added: int,
    ) -> tuple[Evidence, ...]: ...

    def preview_forward_continuation(
        self,
        *,
        seeds: tuple[Evidence, ...],
        procedure_slots: tuple[RequirementSlot, ...],
        caller: TrustedCaller,
        purpose: str,
        max_seeds: int,
        max_added: int,
    ) -> tuple[ExpansionPreview, ...]: ...


@dataclass(frozen=True)
class RecoveryObservation:
    """初次 retrieval 后的 typed Observation；chosen action 尚未执行。"""

    scenario_id: str
    runtime_scope: Literal["business_release", "external_profile"]
    requirement_signature: str
    initial_outcome: RetrievalOutcome
    unsupported_slot_identities: tuple[str, ...]
    eligible_actions: tuple[RecoveryActionId, ...]
    rejected_actions: tuple[RecoveryActionId, ...]
    expansion_previews: tuple[ExpansionPreview, ...] = ()
    continuation_policy: ContinuationPolicy = "disabled"
    trigger_reason_codes: tuple[str, ...] = ()

    def safe_projection(self) -> dict[str, Any]:
        projection = {
            "scenario_id": self.scenario_id,
            "runtime_scope": self.runtime_scope,
            "requirement_signature": self.requirement_signature,
            "initial_outcome": self.initial_outcome.safe_projection(),
            "unsupported_slot_identities": list(self.unsupported_slot_identities),
            "eligible_actions": list(self.eligible_actions),
            "rejected_actions": list(self.rejected_actions),
            "expansion_preview_count": sum(len(item.opaque_candidates) for item in self.expansion_previews),
        }
        # 默认关闭时不改变 P1～P4R 的既有 safe artifact 投影。
        if self.continuation_policy != "disabled":
            projection["continuation_policy"] = self.continuation_policy
            projection["trigger_reason_codes"] = list(self.trigger_reason_codes)
        return projection


@dataclass(frozen=True)
class RecoveryExecution:
    """一次 Scenario 的完整 action-level Evidence 事实。"""

    observation: RecoveryObservation
    chosen_action: RecoveryActionId
    status: Literal["completed", "blocked", "failed", "external_unavailable"]
    evidence_delta: EvidenceDelta
    consumed: ResourceConsumption
    progress: ProgressDecision
    duplicate_key: str
    termination_reason: str
    elapsed_ms: float
    added_evidence: tuple[Evidence, ...] = ()

    def safe_projection(self) -> dict[str, Any]:
        return {
            "observation": self.observation.safe_projection(),
            "chosen_action": self.chosen_action,
            "status": self.status,
            "evidence_delta": self.evidence_delta.safe_projection(),
            "consumed": self.consumed.safe_projection(),
            "progress": self.progress.safe_projection(),
            "duplicate_key": self.duplicate_key,
            "termination_reason": self.termination_reason,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


def _evidence_key(evidence: Evidence) -> str:
    """跨 child run 去重不能依赖 run-bound evidence_id，应使用原件稳定坐标。"""

    return canonical_hash({
        "authority_identity": evidence.ref.authority_identity,
        "revision": evidence.ref.revision,
        "content_identity": evidence.ref.content_identity,
        "anchor": evidence.ref.anchor,
    })


class RAGRecoveryDiagnostic:
    """★ 对外只有 ``observe`` 与 ``execute``：先冻结选择证据，再执行至多一个 action。"""

    identity = "phase4b-rag-recovery-diagnostic-v1"

    def __init__(self, *, budget: RecoveryBudget = RecoveryBudget()) -> None:
        self._budget = budget

    def observe(
        self,
        *,
        scenario_id: str,
        runtime_scope: Literal["business_release", "external_profile"],
        slots: tuple[RequirementSlot, ...],
        tool: KnowledgeTool,
        request: KnowledgeRequest,
        expansion_adapter: ContextExpansionAdapter | None = None,
    ) -> RecoveryObservation:
        """执行唯一 initial retrieval，并只从预签名 slot + 已授权 Evidence 形成 eligible set。"""

        if not scenario_id.strip() or not slots or len({item.identity for item in slots}) != len(slots):
            raise RAGDiagnosticContractError("diagnostic_scenario_invalid")
        if runtime_scope == "business_release" and expansion_adapter is not None:
            raise RAGDiagnosticContractError("business_expansion_adapter_invalid")
        initial = tool.retrieve(request)
        return self.observe_existing(
            scenario_id=scenario_id,
            runtime_scope=runtime_scope,
            slots=slots,
            initial=initial,
            request=request,
            expansion_adapter=expansion_adapter,
        )

    def observe_existing(
        self,
        *,
        scenario_id: str,
        runtime_scope: Literal["business_release", "external_profile"],
        slots: tuple[RequirementSlot, ...],
        initial: RetrievalOutcome,
        request: KnowledgeRequest,
        expansion_adapter: ContextExpansionAdapter | None = None,
        continuation_policy: ContinuationPolicy = "disabled",
    ) -> RecoveryObservation:
        """从已核验的 immutable initial Evidence 重建 Observation，禁止再次检索。

        M45-E 用它把 P3 的同一次 initial retrieval 与新 proposal 做单变量对比。caller、purpose、
        authority 和 ACL 由调用方回源重水化；本方法只执行与 ``observe`` 相同的 coverage/action
        准入，不能接受客户端自报 eligible set。
        """

        if not scenario_id.strip() or not slots or len({item.identity for item in slots}) != len(slots):
            raise RAGDiagnosticContractError("diagnostic_scenario_invalid")
        if runtime_scope == "business_release" and expansion_adapter is not None:
            raise RAGDiagnosticContractError("business_expansion_adapter_invalid")
        if continuation_policy not in {"disabled", "procedure_boundary_v1"}:
            raise RAGDiagnosticContractError("continuation_policy_invalid")
        signature_payload: Any = [item.signature for item in slots]
        if continuation_policy != "disabled":
            signature_payload = {
                "slots": signature_payload,
                "continuation_policy": continuation_policy,
            }
        requirement_signature = canonical_hash(signature_payload)
        unsupported = tuple(slot for slot in slots if not slot.supported_by(initial.selected_evidence))
        previews: tuple[ExpansionPreview, ...] = ()
        trigger_reasons: tuple[str, ...] = ()

        # ★ expansion 只有在“已授权 seed 的相邻 context 能支持当前缺口”时优先成立；这让同一
        # external runtime 根据 Observation 选动作，而不是把 qst ID/corpus 静态映射成动作。
        if unsupported and runtime_scope == "external_profile" and expansion_adapter is not None:
            previews = expansion_adapter.preview(
                seeds=initial.selected_evidence,
                unsupported_slots=unsupported,
                caller=request.caller,
                purpose=request.purpose,
                max_seeds=self._budget.max_expansion_seeds,
                max_sibling_units_scanned_per_seed=self._budget.max_sibling_units_scanned_per_seed,
                max_added=self._budget.max_added_expansion_evidence,
            )
        # ★ coverage 已显示完整时，只有调用方显式开启的新结构策略才能继续。它不猜答案缺口，
        # 只检查 signed query 是否为 procedure 类意图，以及 authority 是否确有紧邻后续 unit。
        if (
            not unsupported
            and continuation_policy == "procedure_boundary_v1"
            and runtime_scope == "external_profile"
            and expansion_adapter is not None
        ):
            procedure_tokens = {"procedure", "workflow", "steps", "checklist"}
            procedure_slots = tuple(
                slot for slot in slots
                if procedure_tokens & set(re.findall(
                    r"[a-z0-9][a-z0-9_-]+", slot.focused_query.casefold()
                ))
            )
            if procedure_slots:
                previews = expansion_adapter.preview_forward_continuation(
                    seeds=initial.selected_evidence,
                    procedure_slots=procedure_slots,
                    caller=request.caller,
                    purpose=request.purpose,
                    max_seeds=self._budget.max_expansion_seeds,
                    max_added=self._budget.max_added_expansion_evidence,
                )
                if previews:
                    trigger_reasons = ("procedure_forward_unit_available",)
        if not unsupported and not previews:
            eligible: tuple[RecoveryActionId, ...] = ("stop",)
        elif previews:
            eligible = ("context_expansion_candidate", "stop")
        else:
            eligible = ("query_rewrite_candidate", "stop")
        rejected = tuple(
            action for action in ("query_rewrite_candidate", "context_expansion_candidate")
            if action not in eligible
        )
        return RecoveryObservation(
            scenario_id=scenario_id,
            runtime_scope=runtime_scope,
            requirement_signature=requirement_signature,
            initial_outcome=initial,
            unsupported_slot_identities=tuple(item.identity for item in unsupported),
            eligible_actions=eligible,
            rejected_actions=rejected,
            expansion_previews=previews,
            continuation_policy=continuation_policy,
            trigger_reason_codes=trigger_reasons,
        )

    def observe_after_rewrite(
        self,
        *,
        prior: RecoveryExecution,
        slots: tuple[RequirementSlot, ...],
        expansion_adapter: ContextExpansionAdapter,
        request: KnowledgeRequest,
    ) -> RecoveryObservation:
        """从已完成 rewrite 的不可变 EvidenceDelta 形成第二个 Observation。

        ★ 这里不再调用 Knowledge Tool，也不重跑 initial/rewrite。新状态只合并第一次 selected
        Evidence 与 rewrite 新增 Evidence；seed 只取 rewrite 新增项，防止把旧 initial 文档静态
        映射成 expansion。每条 seed 仍由 concrete adapter 回 authority 重水化/授权。
        """

        expected_signature = canonical_hash([item.signature for item in slots])
        if (
            prior.chosen_action != "query_rewrite_candidate"
            or prior.status != "completed"
            or not prior.added_evidence
            or prior.observation.requirement_signature != expected_signature
        ):
            raise RAGDiagnosticContractError("rewrite_continuation_invalid")

        combined_by_key: dict[str, Evidence] = {}
        for item in prior.observation.initial_outcome.selected_evidence + prior.added_evidence:
            combined_by_key.setdefault(_evidence_key(item), item)
        combined = tuple(combined_by_key.values())
        unsupported = tuple(slot for slot in slots if not slot.supported_by(combined))
        previews = expansion_adapter.preview(
            seeds=prior.added_evidence,
            unsupported_slots=unsupported,
            caller=request.caller,
            purpose=request.purpose,
            max_seeds=self._budget.max_expansion_seeds,
            max_sibling_units_scanned_per_seed=self._budget.max_sibling_units_scanned_per_seed,
            max_added=self._budget.max_added_expansion_evidence,
        ) if unsupported else ()

        ledger = EvidenceLedger.from_candidates(run_id=request.run_id, evidence=combined)
        if combined:
            ledger = ledger.transition(
                evidence_ids=tuple(item.ref.evidence_id for item in combined), to_stage="selected"
            )
        prior_outcome = prior.observation.initial_outcome
        current_outcome = replace(
            prior_outcome,
            reason_code="recovery_state_rehydrated",
            selected_evidence=combined,
            ledger=ledger,
            pre_generation_authorizations=(),
            diagnostics=replace(
                prior_outcome.diagnostics,
                run_ref=f"continuation:{canonical_hash(request.run_id)[:20]}",
                adapter_calls=0,
                authorized_entry_count=len(combined),
                candidate_count=len(combined),
                selected_count=len(combined),
                elapsed_ms=0.0,
            ),
        )
        eligible: tuple[RecoveryActionId, ...] = (
            ("context_expansion_candidate", "stop") if previews else ("stop",)
        )
        rejected = tuple(
            action for action in ("query_rewrite_candidate", "context_expansion_candidate")
            if action not in eligible
        )
        return RecoveryObservation(
            scenario_id=prior.observation.scenario_id,
            runtime_scope=prior.observation.runtime_scope,
            requirement_signature=expected_signature,
            initial_outcome=current_outcome,
            unsupported_slot_identities=tuple(item.identity for item in unsupported),
            eligible_actions=eligible,
            rejected_actions=rejected,
            expansion_previews=previews,
        )

    def execute(
        self,
        *,
        observation: RecoveryObservation,
        slots: tuple[RequirementSlot, ...],
        tool: KnowledgeTool,
        request: KnowledgeRequest,
        expansion_adapter: ContextExpansionAdapter | None = None,
    ) -> RecoveryExecution:
        """执行 Observation 唯一准入的 recovery；重复/no-progress 均稳定停止。"""

        started = perf_counter()
        candidates = tuple(action for action in observation.eligible_actions if action != "stop")
        chosen: RecoveryActionId = candidates[0] if candidates else "stop"
        duplicate_key = canonical_hash({
            "scenario_id": observation.scenario_id,
            "requirement_signature": observation.requirement_signature,
            "action": chosen,
            "initial_query": observation.initial_outcome.diagnostics.query_fingerprint,
        })
        if chosen == "stop":
            return self._result(
                observation=observation,
                chosen=chosen,
                status="blocked",
                added=(),
                duplicates=(),
                consumed=ResourceConsumption(actions=1, token_usage_observed=True),
                reason="no_recovery_eligible",
                duplicate_key=duplicate_key,
                started=started,
            )

        unsupported_ids = set(observation.unsupported_slot_identities)
        unsupported = tuple(item for item in slots if item.identity in unsupported_ids)
        if chosen == "query_rewrite_candidate":
            added, duplicates, consumed, status = self._execute_rewrite(
                unsupported=unsupported, initial=observation.initial_outcome,
                tool=tool, request=request,
            )
        else:
            if expansion_adapter is None or not observation.expansion_previews:
                raise RAGDiagnosticContractError("expansion_adapter_missing")
            added, duplicates, consumed, status = self._execute_expansion(
                observation=observation, adapter=expansion_adapter, request=request,
            )
        reason = "evidence_gain" if added else "duplicate_or_no_progress"
        return self._result(
            observation=observation, chosen=chosen, status=status, added=added,
            duplicates=duplicates, consumed=consumed, reason=reason,
            duplicate_key=duplicate_key, started=started,
        )

    def _execute_rewrite(
        self,
        *,
        unsupported: tuple[RequirementSlot, ...],
        initial: RetrievalOutcome,
        tool: KnowledgeTool,
        request: KnowledgeRequest,
    ) -> tuple[tuple[Evidence, ...], tuple[str, ...], ResourceConsumption, str]:
        """closed-world focused rewrite：每个 slot 一个子问题，最多两个 retrieval batches。"""

        initial_keys = {_evidence_key(item) for item in initial.selected_evidence}
        added: list[Evidence] = []
        duplicate: list[str] = []
        candidates = selected = batches = 0
        external_unavailable = False
        for index, slot in enumerate(unsupported[: self._budget.max_retrieval_batches], start=1):
            child = tool.retrieve(replace(
                request,
                question=slot.focused_query,
                run_id=f"{request.run_id}:rewrite:{index}:{slot.signature[:12]}",
                budget=RetrievalBudget(
                    max_candidates=self._budget.max_candidates_per_batch,
                    max_selected=self._budget.max_added_evidence,
                ),
            ))
            batches += child.diagnostics.adapter_calls
            candidates += child.diagnostics.candidate_count
            selected += child.diagnostics.selected_count
            external_unavailable = external_unavailable or child.execution_outcome == "external_unavailable"
            for evidence in child.selected_evidence:
                key = _evidence_key(evidence)
                if key in initial_keys or any(_evidence_key(item) == key for item in added):
                    duplicate.append(key)
                    continue
                if len(added) < self._budget.max_added_evidence:
                    added.append(evidence)
        consumed = ResourceConsumption(
            actions=1,
            deep_tools=batches,
            knowledge_actions=batches,
            retrieval_batches=batches,
            candidates=candidates,
            selected=selected,
            model_calls=0,
            total_tokens=0,
            token_usage_observed=True,
        )
        status = "external_unavailable" if external_unavailable and not added else "completed"
        return tuple(added), tuple(duplicate), consumed, status

    def _execute_expansion(
        self,
        *,
        observation: RecoveryObservation,
        adapter: ContextExpansionAdapter,
        request: KnowledgeRequest,
    ) -> tuple[tuple[Evidence, ...], tuple[str, ...], ResourceConsumption, str]:
        """相邻 unit 不走检索/embedding，但仍必须由 adapter 重新授权并构造新 Evidence。"""

        materialized = adapter.materialize(
            previews=observation.expansion_previews,
            caller=request.caller,
            purpose=request.purpose,
            run_id=f"{request.run_id}:expansion",
            max_added=self._budget.max_added_expansion_evidence,
        )
        initial_keys = {_evidence_key(item) for item in observation.initial_outcome.selected_evidence}
        added: list[Evidence] = []
        duplicates: list[str] = []
        for evidence in materialized:
            key = _evidence_key(evidence)
            if key in initial_keys or any(_evidence_key(item) == key for item in added):
                duplicates.append(key)
            elif len(added) < 4:
                added.append(evidence)
        consumed = ResourceConsumption(
            actions=1,
            deep_tools=0,
            knowledge_actions=0,
            retrieval_batches=0,
            candidates=len(materialized),
            selected=len(added),
            model_calls=0,
            total_tokens=0,
            token_usage_observed=True,
        )
        return tuple(added), tuple(duplicates), consumed, "completed"

    @staticmethod
    def _result(
        *,
        observation: RecoveryObservation,
        chosen: RecoveryActionId,
        status: str,
        added: tuple[Evidence, ...],
        duplicates: tuple[str, ...],
        consumed: ResourceConsumption,
        reason: str,
        duplicate_key: str,
        started: float,
    ) -> RecoveryExecution:
        """从实际新增/重复 Evidence 统一投影 Delta、Progress 和稳定终止原因。"""

        delta = EvidenceDelta(
            added=tuple(item.safe_projection()["ref"] for item in added),
            duplicate=duplicates,
        )
        progress = ProgressDecision(
            coverage_increased=bool(added),
            eligible_action_remains=False,
            reason_code=reason,
        )
        return RecoveryExecution(
            observation=observation,
            chosen_action=chosen,
            status=status,  # type: ignore[arg-type]
            evidence_delta=delta,
            consumed=consumed,
            progress=progress,
            duplicate_key=duplicate_key,
            termination_reason="action_completed" if added else "no_progress",
            elapsed_ms=(perf_counter() - started) * 1000,
            added_evidence=added,
        )
