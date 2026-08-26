"""M46-C/D：一次父级 Knowledge action 内的有界 RAG Subgraph。

这个模块不生成答案，也不拥有 Answer Gate。它只把 initial retrieval 和至多两次已准入的
recovery action 收敛成一份重新授权的 ``RetrievalOutcome``。可以把它看作 Controller 内部的
小流水线：父 Loop 只看见一次“取文档证据”，子图自己负责观察、记账和停止。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any, Callable, Literal, Mapping, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from engine.governance import AuthorizationDecision, TrustedCaller, authorize_document
from engine.phase4b.b4_contracts import load_b4_contract_bundle
from engine.phase4b.external_requirement_formation import (
    ExternalRequirementFormationInput,
    ExternalRequirementFormer,
    FormedRequirement,
)
from engine.phase4b.rag_diagnostics import (
    ContextExpansionAdapter,
    RAGDiagnosticContractError,
    RAGRecoveryDiagnostic,
    RecoveryExecution,
    RecoveryObservation,
    RequirementSlot,
)
from engine.rag.catalog import CatalogEntry
from engine.rag.evidence import (
    DocumentEvidencePayload,
    Evidence,
    EvidenceContractError,
    EvidenceLedger,
    make_document_evidence,
)
from engine.rag.evidence_acquisition import AcquisitionResult, ActiveLoader, DocumentEvidenceAcquirer
from engine.rag.knowledge_tool import (
    KnowledgeRequest,
    KnowledgeTool,
    KnowledgeToolContractError,
    RetrievalDiagnostics,
    RetrievalOutcome,
)
from engine.rag.retrieval import RetrievalAdapterError, RetrievalBudget

if False:  # pragma: no cover - 只帮助静态阅读，避免 answer_flow 循环导入。
    from engine.rag.answer_flow import RAGAnswerRequest

B4_BUNDLE = load_b4_contract_bundle()

RecoveryAction = Literal["query_rewrite_candidate", "context_expansion_candidate", "stop"]
SubgraphTermination = Literal[
    "answer_ready", "insufficient_coverage", "no_progress", "budget_exhausted", "unsafe",
    "external_unavailable", "contract_failure",
]


class RAGSubgraphContractError(ValueError):
    """子图的策略/预算/授权输入不闭合时失败关闭。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ChildConsumption:
    """父动作内部的真实消费；不复用 B2 的单 retrieval 字段以免改写旧合同。"""

    initial_retrieval_batches: int = 0
    rewrite_retrieval_batches: int = 0
    expansion_candidates_scanned: int = 0
    expansion_evidence_added: int = 0
    candidates_examined: int = 0
    unique_merged_evidence: int = 0
    selected: int = 0
    generation_visible: int = 0
    proposal_calls: int = 0
    model_calls: int = 0
    total_tokens: int = 0
    token_usage_observed: bool = True
    retrieval_attempts_observed: bool = True
    latency_ms: float = 0.0

    def add(self, other: "ChildConsumption") -> "ChildConsumption":
        """逐维累加；token 未观测时保持未知而不是伪造为零。"""

        return ChildConsumption(
            initial_retrieval_batches=self.initial_retrieval_batches + other.initial_retrieval_batches,
            rewrite_retrieval_batches=self.rewrite_retrieval_batches + other.rewrite_retrieval_batches,
            expansion_candidates_scanned=self.expansion_candidates_scanned + other.expansion_candidates_scanned,
            expansion_evidence_added=self.expansion_evidence_added + other.expansion_evidence_added,
            candidates_examined=self.candidates_examined + other.candidates_examined,
            unique_merged_evidence=self.unique_merged_evidence + other.unique_merged_evidence,
            selected=self.selected + other.selected,
            generation_visible=self.generation_visible + other.generation_visible,
            proposal_calls=self.proposal_calls + other.proposal_calls,
            model_calls=self.model_calls + other.model_calls,
            total_tokens=self.total_tokens + other.total_tokens,
            token_usage_observed=self.token_usage_observed and other.token_usage_observed,
            retrieval_attempts_observed=(
                self.retrieval_attempts_observed and other.retrieval_attempts_observed
            ),
            latency_ms=round(self.latency_ms + other.latency_ms, 3),
        )

    def safe_projection(self) -> dict[str, Any]:
        """把一次 recovery 压缩为不含 query、正文与 provider 原文的 timeline 行。"""

        """只公开消费数字，不公开 query、正文、slot marker 或 provider 原文。"""

        return dict(self.__dict__)


@dataclass(frozen=True)
class ChildAttempt:
    """一次 recovery action 的安全 timeline 行。"""

    ordinal: int
    action: RecoveryAction
    status: str
    eligible_actions: tuple[RecoveryAction, ...]
    rejected_actions: tuple[RecoveryAction, ...]
    evidence_added: int
    duplicate_count: int
    consumption: ChildConsumption
    progress_reason: str

    def safe_projection(self) -> dict[str, Any]:
        """把一次 recovery 压缩为不含 query、正文与 provider 原文的 timeline 行。"""

        return {
            "ordinal": self.ordinal,
            "action": self.action,
            "status": self.status,
            "eligible_actions": list(self.eligible_actions),
            "rejected_actions": list(self.rejected_actions),
            "evidence_added": self.evidence_added,
            "duplicate_count": self.duplicate_count,
            "consumption": self.consumption.safe_projection(),
            "progress_reason": self.progress_reason,
        }


@dataclass(frozen=True)
class ChildLedger:
    """B4 child timeline；它与 B2 父账分开，但最终会聚合回父 ActionAttempt。"""

    attempts: tuple[ChildAttempt, ...] = ()
    consumption: ChildConsumption = ChildConsumption()
    termination: SubgraphTermination = "insufficient_coverage"
    detail_code: str = "initial_not_observed"
    admission_decision: str = "not_observed"
    admission_reason_code: str = "not_observed"
    formed_requirements: tuple[Mapping[str, Any], ...] = ()

    def with_attempt(self, attempt: ChildAttempt) -> "ChildLedger":
        """维护 ordinal/预算守恒，拒绝同一 action 无限循环。"""

        if attempt.ordinal != len(self.attempts) + 1:
            raise RAGSubgraphContractError("child_attempt_ordinal_invalid")
        if len(self.attempts) >= int(B4_BUNDLE.payload["child_budget"]["max_recovery_actions"]):
            raise RAGSubgraphContractError("child_budget_exhausted")
        updated = replace(self, attempts=(*self.attempts, attempt), consumption=self.consumption.add(attempt.consumption))
        updated._validate_budget()
        return updated

    def stopped(self, *, termination: SubgraphTermination, detail_code: str) -> "ChildLedger":
        """以 typed termination 冻结 child ledger，不隐式追加新动作。"""

        return replace(self, termination=termination, detail_code=detail_code)

    def _validate_budget(self) -> None:
        """在下一 child 调用前和每次实际消费后复核 B4 固定上限。"""

        limit = B4_BUNDLE.payload["child_budget"]
        consumed = self.consumption
        if (
            consumed.initial_retrieval_batches > int(limit["max_initial_retrieval_batches"])
            or consumed.rewrite_retrieval_batches > int(limit["max_rewrite_retrieval_batches"])
            or consumed.initial_retrieval_batches + consumed.rewrite_retrieval_batches > int(limit["max_total_retrieval_batches"])
            or consumed.candidates_examined > int(limit["max_total_candidates"])
            or consumed.expansion_candidates_scanned > (
                int(limit["max_expansion_seeds"])
                * int(limit["max_sibling_units_scanned_per_seed"])
            )
            or consumed.expansion_evidence_added > int(limit["max_added_expansion_evidence"])
            or consumed.unique_merged_evidence > int(limit["max_unique_merged_evidence"])
            or consumed.selected > int(limit["max_selected"])
            or consumed.generation_visible > int(limit["max_generation_visible"])
            or consumed.proposal_calls > int(limit["max_proposal_calls"])
            or consumed.model_calls > int(limit["max_model_calls"])
            or (consumed.token_usage_observed and consumed.total_tokens > int(limit["max_total_tokens"]))
        ):
            raise RAGSubgraphContractError("child_budget_exhausted")

    def safe_projection(self) -> dict[str, Any]:
        """输出可进入父 Observation 的 B4 child 安全投影。"""

        return {
            "attempts": [item.safe_projection() for item in self.attempts],
            "consumption": self.consumption.safe_projection(),
            "termination": self.termination,
            "detail_code": self.detail_code,
            # 只允许固定枚举；它说明 deterministic admission 为什么未形成 slot，不暴露题面、
            # token、正文、文档身份或计数，供 Live Probe 在不保存私有输入的前提下排障。
            "admission_decision": self.admission_decision,
            "admission_reason_code": self.admission_reason_code,
            "formed_requirements": [dict(item) for item in self.formed_requirements],
        }


class RequirementSlotProvider(Protocol):
    """把 server-owned requirement 或受控 proposal 转成 action eligibility 的 typed slot。"""

    identity: str

    def resolve(
        self, *, request: "RAGAnswerRequest", initial: RetrievalOutcome
    ) -> "SlotResolution":
        """根据 server-owned facts 形成有限的 typed recovery slots。"""

        ...


@dataclass(frozen=True)
class SlotResolution:
    """server-owned slot 形成的结果；proposal usage 在这里进入 child ledger。"""

    slots: tuple[RequirementSlot, ...]
    formed_requirements: tuple[FormedRequirement, ...] = ()
    continuation_policy: Literal["disabled", "procedure_boundary_v1"] = "disabled"
    proposal_calls: int = 0
    model_calls: int = 0
    total_tokens: int = 0
    token_usage_observed: bool = True
    decision: str = "deterministic"
    admission_reason_code: str = "not_applicable"
    failure_reason: str | None = None


class BusinessT4SlotProvider:
    """仅服务 B0/T4 的 server-owned policy requirement，避免客户输入 document key 选动作。"""

    identity = "phase4b-b4-business-t4-slots-v1"

    def resolve(self, *, request: "RAGAnswerRequest", initial: RetrievalOutcome) -> SlotResolution:
        """仅为固定 business T4 requirement 返回服务端预定义 slots。"""

        del initial
        required = set(request.requirement.required_document_keys)
        if required != {"refund_policy_basic", "refund_policy_quality"}:
            return SlotResolution((), decision="business_requirement_not_applicable")
        return SlotResolution((
            RequirementSlot(
                "policy_scope", "退款政策适用范围、支持的退款原因与基础总则",
                (("7 天无理由", "七天无理由"), ("物流损坏",), ("价保补差",)),
            ),
            RequirementSlot(
                "required_materials", "质量问题退款需要哪些申请材料和补充证据",
                (("订单号",), ("照片",), ("视频",)),
            ),
            RequirementSlot(
                "processing_conditions", "质量问题全额退款的确认前提和处理路径",
                (("质检确认",), ("原支付路径",), ("全额退款",)),
            ),
        ))


class ExternalFormationSlotProvider:
    """把 C2-ERF deep module 适配到既有 Subgraph slot seam。"""

    identity = "phase4b-b4-external-formation-slot-adapter-v1"

    def __init__(self, former: ExternalRequirementFormer) -> None:
        self._former = former

    def resolve(self, *, request: "RAGAnswerRequest", initial: RetrievalOutcome) -> SlotResolution:
        """调用 external former，并把结果适配为子图可消费的 slot facts。"""

        result = self._former.form(ExternalRequirementFormationInput(
            question=request.question,
            current_evidence=initial.selected_evidence,
        ))
        return SlotResolution(
            slots=tuple(item.slot for item in result.requirements),
            formed_requirements=result.requirements,
            continuation_policy=result.continuation_policy,
            proposal_calls=result.usage.calls,
            model_calls=result.usage.calls,
            total_tokens=result.usage.total_tokens,
            token_usage_observed=result.usage.token_usage_observed,
            decision=result.decision,
            admission_reason_code=result.reason_code,
            failure_reason=result.failure_reason,
        )


class _SubgraphState(TypedDict, total=False):
    """B4 子图进程内状态；不直接作为 Trace 或 Eval artifact。"""

    observation: RecoveryObservation
    execution: RecoveryExecution
    executions: tuple[RecoveryExecution, ...]


def _recovery_first_sources(
    *, initial: RetrievalOutcome, executions: tuple[RecoveryExecution, ...]
) -> tuple[Evidence, ...]:
    """按“最新 recovery → 较早 recovery → initial”形成最终重授权顺序。

    initial 往往已经占满 3 条 selected 上限。如果仍按 initial-first 合并，子图刚找回的
    Evidence 会在截断时全部丢失，等于动作执行了却没有进入 Answer Gate。这里不看 gold、
    title 或正文分数，只使用已经由 Observation 准入的 action lineage 做稳定排序。
    """

    recovered = tuple(
        item
        for execution in reversed(executions)
        for item in execution.added_evidence
    )
    return (*recovered, *initial.selected_evidence)


def _safe_runtime_failure_code(*, stage: str, exc: Exception) -> str:
    """只公开 allowlist exception family；永不回显 message、query 或 provider payload。"""

    if isinstance(exc, KnowledgeToolContractError):
        category = "knowledge_tool_contract"
    elif isinstance(exc, RetrievalAdapterError):
        category = "retrieval_adapter"
    elif isinstance(exc, EvidenceContractError):
        safe_reasons = {
            "evidence_invalid",
            "evidence_unauthorized",
            "evidence_purpose_invalid",
            "evidence_revision_unavailable",
            "evidence_run_mismatch",
            "evidence_unknown",
            "evidence_transition_invalid",
        }
        reason = exc.reason_code if exc.reason_code in safe_reasons else "unknown"
        category = f"evidence_contract_{reason}"
    elif isinstance(exc, KeyError):
        category = "key_error"
    elif isinstance(exc, TypeError):
        category = "type_error"
    elif isinstance(exc, AttributeError):
        category = "attribute_error"
    elif isinstance(exc, ValueError):
        category = "value_error"
    else:
        category = "unexpected"
    return f"subgraph_{stage}_{category}_failure"


class BoundedRAGSubgraphAcquirer:
    """C2 的真实 LangGraph implementation，输出仍是 C1 的统一 acquisition result。"""

    identity = "phase4b-bounded-rag-subgraph-acquisition-v1"

    def __init__(
        self,
        *,
        initial_acquirer: DocumentEvidenceAcquirer,
        knowledge_tool: KnowledgeTool,
        active_loader: ActiveLoader,
        slot_provider: RequirementSlotProvider,
        runtime_scope: Literal["business_release", "external_profile"],
        expansion_adapter: ContextExpansionAdapter | None = None,
    ) -> None:
        self._initial_acquirer = initial_acquirer
        self._knowledge_tool = knowledge_tool
        self._active_loader = active_loader
        self._slot_provider = slot_provider
        self._runtime_scope = runtime_scope
        self._expansion_adapter = expansion_adapter
        if runtime_scope == "business_release" and expansion_adapter is not None:
            raise RAGSubgraphContractError("business_expansion_adapter_invalid")

    def acquire(self, *, request: "RAGAnswerRequest", started_at: float) -> AcquisitionResult:
        """initial → observe → action → observe/stop，并将所有最终 Evidence 回源重授权。"""

        initial = self._initial_acquirer.acquire(request=request, started_at=started_at)
        initial_outcome = initial.outcome
        initial_consumption = ChildConsumption(
            initial_retrieval_batches=initial_outcome.diagnostics.adapter_calls,
            candidates_examined=initial_outcome.diagnostics.candidate_count,
            unique_merged_evidence=len(initial_outcome.selected_evidence),
            selected=initial_outcome.diagnostics.selected_count,
            generation_visible=0,
            latency_ms=initial_outcome.diagnostics.elapsed_ms,
        )
        ledger = ChildLedger(consumption=initial_consumption)
        try:
            ledger._validate_budget()
        except RAGSubgraphContractError:
            return self._result(initial, ledger.stopped(termination="budget_exhausted", detail_code="initial_budget_overrun"))
        if initial_outcome.execution_outcome != "completed" or not initial_outcome.selected_evidence:
            return self._result(
                initial,
                ledger.stopped(
                    termination="external_unavailable" if initial_outcome.execution_outcome == "external_unavailable" else "insufficient_coverage",
                    detail_code=initial_outcome.reason_code,
                ),
            )
        resolution = self._slot_provider.resolve(request=request, initial=initial_outcome)
        ledger = replace(
            ledger,
            admission_decision=resolution.decision,
            admission_reason_code=resolution.admission_reason_code,
            formed_requirements=tuple(
                item.safe_projection() for item in resolution.formed_requirements
            ),
            consumption=ledger.consumption.add(ChildConsumption(
                proposal_calls=resolution.proposal_calls,
                model_calls=resolution.model_calls,
                total_tokens=resolution.total_tokens,
                token_usage_observed=resolution.token_usage_observed,
            )),
        )
        try:
            ledger._validate_budget()
        except RAGSubgraphContractError:
            return self._result(initial, ledger.stopped(termination="budget_exhausted", detail_code="proposal_budget_overrun"))
        slots = resolution.slots
        if not slots:
            return self._result(initial, ledger.stopped(
                termination="contract_failure" if resolution.failure_reason else "insufficient_coverage",
                detail_code=resolution.failure_reason or "slot_provider_no_action",
            ))

        diagnostic = RAGRecoveryDiagnostic()
        allowed_recovery_actions = frozenset(
            action
            for requirement in resolution.formed_requirements
            for action in requirement.allowed_recovery_actions
        )
        knowledge_request = KnowledgeRequest(
            question=request.question,
            caller=request.caller,
            purpose=request.purpose,
            run_id=request.run_id,
            budget=request.retrieval_budget,
            confirmed_conditions=request.confirmed_conditions,
        )

        runtime_stage = {"value": "compile"}

        def observe_node(state: _SubgraphState) -> dict[str, Any]:
            """观察当前 coverage，并产生下一步 action eligibility。"""

            runtime_stage["value"] = "observe"
            previous = state.get("execution")
            if previous is not None and previous.chosen_action == "query_rewrite_candidate" and previous.added_evidence:
                if self._expansion_adapter is None:
                    # business 只有 rewrite card。首个 recovery action 内已可使用最多两个 focused
                    # retrieval batch；不能因为“没有 expansion adapter”把同一 Observation 再执行一次。
                    return {"observation": replace(
                        previous.observation,
                        eligible_actions=("stop",),
                        rejected_actions=("query_rewrite_candidate", "context_expansion_candidate"),
                    )}
                observation = diagnostic.observe_after_rewrite(
                    prior=previous,
                    slots=slots,
                    expansion_adapter=self._expansion_adapter,
                    request=knowledge_request,
                )
            else:
                observation = diagnostic.observe_existing(
                    scenario_id="B4_RUNTIME",
                    runtime_scope=self._runtime_scope,
                    slots=slots,
                    initial=initial_outcome,
                    request=knowledge_request,
                    expansion_adapter=self._expansion_adapter,
                    continuation_policy=resolution.continuation_policy,
                )
            if allowed_recovery_actions:
                eligible = tuple(
                    action
                    for action in observation.eligible_actions
                    if action == "stop" or action in allowed_recovery_actions
                )
                rejected = tuple(dict.fromkeys((
                    *observation.rejected_actions,
                    *(
                        action for action in ("query_rewrite_candidate", "context_expansion_candidate")
                        if action not in allowed_recovery_actions
                    ),
                )))
                observation = replace(
                    observation,
                    eligible_actions=eligible or ("stop",),
                    rejected_actions=rejected,
                )
            return {"observation": observation}

        def execute_node(state: _SubgraphState) -> dict[str, Any]:
            """严格执行 observation 已授权的一次 recovery action。"""

            runtime_stage["value"] = "execute"
            observation = state["observation"]
            execution = diagnostic.execute(
                observation=observation,
                slots=slots,
                tool=self._knowledge_tool,
                request=knowledge_request,
                expansion_adapter=self._expansion_adapter,
            )
            return {"execution": execution, "executions": (*state.get("executions", ()), execution)}

        def route_after_observe(state: _SubgraphState) -> str:
            """没有可执行 recovery action 时直接 typed stop。"""

            return "execute" if any(action != "stop" for action in state["observation"].eligible_actions) else "stop"

        def route_after_execute(state: _SubgraphState) -> str:
            """仅在首次 rewrite 确有新增 Evidence 时允许再观察一次。"""

            execution = state["execution"]
            if (
                execution.chosen_action == "query_rewrite_candidate"
                and execution.status == "completed"
                and bool(execution.added_evidence)
                and len(state.get("executions", ())) < 2
            ):
                return "observe"
            return "stop"

        graph = StateGraph(_SubgraphState)
        graph.add_node("observe", observe_node)
        graph.add_node("execute", execute_node)
        graph.add_edge(START, "observe")
        graph.add_conditional_edges("observe", route_after_observe, {"execute": "execute", "stop": END})
        graph.add_conditional_edges("execute", route_after_execute, {"observe": "observe", "stop": END})
        try:
            state = graph.compile().invoke({"executions": ()}, config={"recursion_limit": 8})
        except (RAGDiagnosticContractError, RAGSubgraphContractError):
            return self._result(initial, ledger.stopped(termination="contract_failure", detail_code="subgraph_contract_failure"))
        except Exception as exc:  # noqa: BLE001 - 只投影 allowlist 类别，不泄露 adapter message。
            if runtime_stage["value"] == "execute":
                ledger = replace(
                    ledger,
                    consumption=replace(
                        ledger.consumption,
                        retrieval_attempts_observed=False,
                    ),
                )
            return self._result(initial, ledger.stopped(
                termination="contract_failure",
                detail_code=_safe_runtime_failure_code(stage=runtime_stage["value"], exc=exc),
            ))

        executions = tuple(state.get("executions", ()))
        try:
            for ordinal, execution in enumerate(executions, start=1):
                is_rewrite = execution.chosen_action == "query_rewrite_candidate"
                is_expansion = execution.chosen_action == "context_expansion_candidate"
                consumption = ChildConsumption(
                    rewrite_retrieval_batches=execution.consumed.retrieval_batches if is_rewrite else 0,
                    # expansion preview 与 retrieval candidate 是两本账：前者受 seed×scan 上限，
                    # 不能再挤占 max_total_candidates=15 的 embedding retrieval 预算。
                    expansion_candidates_scanned=sum(
                        len(preview.opaque_candidates)
                        for preview in execution.observation.expansion_previews
                    ) if is_expansion else 0,
                    expansion_evidence_added=len(execution.added_evidence) if is_expansion else 0,
                    candidates_examined=execution.consumed.candidates if is_rewrite else 0,
                    unique_merged_evidence=len(execution.added_evidence),
                    selected=0,
                    generation_visible=0,
                    latency_ms=execution.elapsed_ms,
                )
                ledger = ledger.with_attempt(ChildAttempt(
                    ordinal=ordinal,
                    action=execution.chosen_action,
                    status=execution.status,
                    eligible_actions=execution.observation.eligible_actions,
                    rejected_actions=execution.observation.rejected_actions,
                    evidence_added=len(execution.added_evidence),
                    duplicate_count=len(execution.evidence_delta.duplicate),
                    consumption=consumption,
                    progress_reason=execution.progress.reason_code,
                ))
        except RAGSubgraphContractError:
            return self._result(initial, ledger.stopped(termination="budget_exhausted", detail_code="recovery_budget_overrun"))

        added = tuple(item for execution in executions for item in execution.added_evidence)
        if not added:
            reason = "no_progress" if executions else "insufficient_coverage"
            return self._result(initial, ledger.stopped(termination=reason, detail_code="no_recovery_evidence_gain"))
        try:
            merged = self._reauthorize_and_merge(
                request=request,
                initial=initial_outcome,
                sources=_recovery_first_sources(initial=initial_outcome, executions=executions),
            )
        except RAGSubgraphContractError as exc:
            termination: SubgraphTermination = "unsafe" if exc.reason_code == "recovery_reauthorization_denied" else "contract_failure"
            return self._result(initial, ledger.stopped(termination=termination, detail_code=exc.reason_code))
        # selected/generation-visible 是最终 Authorize/Gate 的事实，不应把中间 candidate 数误投影
        # 成 AnswerFlow context 数；此时 Gate 尚未运行，所以 generation-visible 仍为零。
        merged_ledger = replace(
            ledger,
            consumption=replace(ledger.consumption, selected=len(merged.selected_evidence), generation_visible=0),
        ).stopped(termination="answer_ready", detail_code="recovery_evidence_merged")
        return self._result(initial, merged_ledger, outcome=merged)

    def _reauthorize_and_merge(
        self,
        *,
        request: "RAGAnswerRequest",
        initial: RetrievalOutcome,
        sources: tuple[Evidence, ...],
    ) -> RetrievalOutcome:
        """每条 initial/recovery Evidence 回当前 authority 重水化，并重做双 ACL。"""

        try:
            _pointer, bundle = self._active_loader()
        except Exception as exc:  # noqa: BLE001
            raise RAGSubgraphContractError("recovery_authority_unavailable") from exc
        indexed = {(entry.document_key, entry.revision): entry for entry in bundle.entries}
        selected: list[Evidence] = []
        authorizations: list[tuple[str, AuthorizationDecision]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for source in sources:
            if not isinstance(source.payload, DocumentEvidencePayload):
                raise RAGSubgraphContractError("recovery_evidence_type_invalid")
            payload = source.payload
            entry = indexed.get((payload.document_key, payload.revision))
            if (
                entry is None
                or entry.status != "active"
                or entry.content_identity != source.ref.content_identity
                or entry.anchor != source.ref.anchor
                or entry.authority_ref != source.ref.authority_identity
            ):
                raise RAGSubgraphContractError("recovery_identity_drift")
            key = (entry.authority_ref, entry.revision, entry.content_identity, entry.anchor)
            if key in seen:
                continue
            pre_selection = authorize_document(
                caller=request.caller, entry=entry, purpose=request.purpose, phase="pre_selection"
            )
            pre_generation = authorize_document(
                caller=request.caller, entry=entry, purpose=request.purpose, phase="pre_generation"
            )
            if not pre_selection.allowed or not pre_generation.allowed:
                raise RAGSubgraphContractError("recovery_reauthorization_denied")
            selected_item = make_document_evidence(
                run_id=request.run_id,
                release_identity=bundle.release_identity,
                entry=entry,
                purpose=request.purpose,
                authorization=pre_selection,
                runtime_ref=f"subgraph:{self.identity}",
                context_coordinates=payload.context_coordinates,
            )
            selected.append(selected_item)
            authorizations.append((selected_item.ref.evidence_id, pre_generation))
            seen.add(key)
        if not selected:
            raise RAGSubgraphContractError("recovery_no_authorized_evidence")
        # ★ 只保留 AnswerFlow 当前 Gate 可接受的 selected 上限；超出的候选已经记在 child ledger，
        # 不能悄悄塞进 Composer context 逃避既有 context budget。
        selected = selected[: int(B4_BUNDLE.payload["child_budget"]["max_selected"])]
        selected_ids = tuple(item.ref.evidence_id for item in selected)
        ledger = EvidenceLedger.from_candidates(run_id=request.run_id, evidence=tuple(selected)).transition(
            evidence_ids=selected_ids, to_stage="selected"
        )
        return RetrievalOutcome(
            execution_outcome="completed",
            reason_code="evidence_retrieved",
            selected_evidence=tuple(selected),
            ledger=ledger,
            pre_generation_authorizations=tuple((evidence_id, auth) for evidence_id, auth in authorizations if evidence_id in set(selected_ids)),
            diagnostics=replace(
                initial.diagnostics,
                adapter_identity=self.identity,
                recipe_identity=str(B4_BUNDLE.payload["runtime_identity"]),
                adapter_calls=initial.diagnostics.adapter_calls,
                authorized_entry_count=len(selected),
                candidate_count=max(initial.diagnostics.candidate_count, len(selected)),
                selected_count=len(selected),
                elapsed_ms=initial.diagnostics.elapsed_ms,
            ),
        )

    def _result(
        self,
        initial: AcquisitionResult,
        ledger: ChildLedger,
        *,
        outcome: RetrievalOutcome | None = None,
    ) -> AcquisitionResult:
        """把 child ledger 与最终 outcome 封装回 acquisition seam。"""

        result = outcome or self._stopped_outcome(initial.outcome, ledger)
        validity = {
            **initial.evidence_validity,
            "acquisition_strategy_identity": self.identity,
            "subgraph": ledger.safe_projection(),
            "slot_provider_identity": self._slot_provider.identity,
        }
        return AcquisitionResult(result, validity, self.identity)

    @staticmethod
    def _stopped_outcome(initial: RetrievalOutcome, ledger: ChildLedger) -> RetrievalOutcome:
        """非 answer-ready 子图不能把 initial partial Evidence 继续交给 Gate/Composer。

        ``RetrievalOutcome`` 的公开 reason 闭集早于 B4，因此精确 root cause 留在 private child
        ledger；这里映射到既有 typed stop，避免为 M46 原地改写 C1/AnswerFlow 核心合同。
        """

        if ledger.termination == "unsafe":
            execution_outcome = "completed"
            reason_code = "no_authorized_evidence"
        elif ledger.termination in {"insufficient_coverage", "no_progress", "budget_exhausted"}:
            execution_outcome = "completed"
            reason_code = "no_candidate"
        else:
            execution_outcome = "external_unavailable"
            reason_code = "retrieval_unavailable"
        empty_ledger = EvidenceLedger.from_candidates(
            run_id=initial.ledger.run_id,
            evidence=(),
        )
        return replace(
            initial,
            execution_outcome=execution_outcome,
            reason_code=reason_code,
            selected_evidence=(),
            ledger=empty_ledger,
            pre_generation_authorizations=(),
            diagnostics=replace(
                initial.diagnostics,
                selected_count=0,
            ),
        )
