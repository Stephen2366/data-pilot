"""M46-B：Document Evidence Acquisition 的稳定深 seam。

``RAGAnswerFlow`` 只需要一份已经完成取证的 ``RetrievalOutcome``，不应该知道初次检索、
业务 Evidence 重水化或未来 B4 Subgraph 怎样运行。这个 seam 像后端里的 repository interface：
上层只消费统一返回值，复杂的取数策略被关在实现内部。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import TYPE_CHECKING, Any, Callable, Protocol

from engine.governance import AuthorizationDecision, authorize_document
from engine.rag.catalog import CatalogEntry
from engine.rag.evidence import Evidence, EvidenceLedger, EvidenceRef, make_document_evidence
from engine.rag.knowledge_tool import (
    ExecutionOutcome as RetrievalExecutionOutcome,
    KnowledgeBundleView,
    KnowledgeRequest,
    KnowledgeTool,
    RetrievalDiagnostics,
    RetrievalOutcome,
    RetrievalReason,
)
from engine.rag.release import ReleaseError
from engine.rag.retrieval import query_fingerprint

if TYPE_CHECKING:
    from engine.rag.answer_flow import RAGAnswerRequest

ActiveLoader = Callable[[], tuple[object, KnowledgeBundleView]]


@dataclass(frozen=True)
class AcquisitionResult:
    """取证策略交给 AnswerFlow 的唯一结果，不复制 Gate/Composer/citation 所有权。"""

    outcome: RetrievalOutcome
    evidence_validity: dict[str, Any]
    strategy_identity: str


class DocumentEvidenceAcquirer(Protocol):
    """C1 小 interface：调用方看不到子图 state、动作或 provider 细节。"""

    identity: str

    def acquire(self, *, request: "RAGAnswerRequest", started_at: float) -> AcquisitionResult:
        """返回同一轮已选择的 Evidence 与完整授权账本。"""


class PipelineEvidenceAcquirer:
    """兼容基线：封装 M32/M37 的一次检索与业务窄重水化。

    ★ 这里是可独立测试的 baseline，不是为子图额外包一层的 pass-through。它拥有旧 Pipeline
    的所有 acquisition 决策；AnswerFlow 以后只保留 Gate、Composer 与 Citation 的职责。
    """

    identity = "rag-document-evidence-acquisition-pipeline-v1"

    def __init__(self, *, knowledge_tool: KnowledgeTool, active_loader: ActiveLoader) -> None:
        self._knowledge_tool = knowledge_tool
        self._active_loader = active_loader

    def acquire(self, *, request: "RAGAnswerRequest", started_at: float) -> AcquisitionResult:
        """只执行一次 Pipeline retrieval，或执行已存在的 business rehydrate 合同。"""

        def retrieve(reason: str) -> AcquisitionResult:
            outcome = self._knowledge_tool.retrieve(
                KnowledgeRequest(
                    question=request.question,
                    caller=request.caller,
                    purpose=request.purpose,
                    run_id=request.run_id,
                    budget=request.retrieval_budget,
                    confirmed_conditions=request.confirmed_conditions,
                )
            )
            return AcquisitionResult(
                outcome,
                {
                    "runtime_kind": request.knowledge_runtime_kind,
                    "requirement_equivalent": request.requirement_equivalent,
                    "decision": "reacquired",
                    "reason": reason,
                    "old_new_relation": "not_comparable",
                },
                self.identity,
            )

        if not request.prior_evidence_refs:
            return retrieve("initial_or_no_prior_evidence")
        if request.knowledge_runtime_kind == "external_profile":
            return retrieve("external_profile_always_retrieves")
        if not request.requirement_equivalent:
            return retrieve("requirement_changed")

        # 业务专用 locator 只读取当前 active bundle；没有正文缓存，也不接受 external profile。
        try:
            _pointer, bundle = self._active_loader()
        except ReleaseError:
            return AcquisitionResult(
                self._empty_rehydrate_outcome(
                    request=request,
                    started_at=started_at,
                    bundle=None,
                    reason_code="active_release_unavailable",
                    execution_outcome="external_unavailable",
                ),
                {
                    "runtime_kind": "business_release",
                    "requirement_equivalent": True,
                    "decision": "unavailable",
                    "reason": "active_release_unavailable",
                    "old_new_relation": "unavailable",
                },
                self.identity,
            )

        located: list[CatalogEntry] = []
        for ref in request.prior_evidence_refs:
            matches = [
                entry
                for entry in bundle.entries
                if entry.authority_ref == ref.authority_identity
                and entry.revision == ref.revision
                and entry.content_identity == ref.content_identity
                and entry.anchor == ref.anchor
                and entry.status == "active"
            ]
            if len(matches) != 1:
                return retrieve("document_identity_changed")
            located.append(matches[0])

        candidates: list[Evidence] = []
        generation_auth: list[tuple[str, AuthorizationDecision]] = []
        for entry in located:
            pre_selection = authorize_document(
                caller=request.caller, entry=entry, purpose=request.purpose, phase="pre_selection"
            )
            pre_generation = authorize_document(
                caller=request.caller, entry=entry, purpose=request.purpose, phase="pre_generation"
            )
            if not pre_selection.allowed or not pre_generation.allowed:
                return AcquisitionResult(
                    self._empty_rehydrate_outcome(
                        request=request,
                        started_at=started_at,
                        bundle=bundle,
                        reason_code="no_authorized_evidence",
                        execution_outcome="completed",
                    ),
                    {
                        "runtime_kind": "business_release",
                        "requirement_equivalent": True,
                        "decision": "denied",
                        "reason": "reauthorization_denied",
                        "old_new_relation": "undisclosed",
                    },
                    self.identity,
                )
            evidence = make_document_evidence(
                run_id=request.run_id,
                release_identity=bundle.release_identity,
                entry=entry,
                purpose=request.purpose,
                authorization=pre_selection,
                runtime_ref="rehydrate:business-active-identity-v1",
            )
            candidates.append(evidence)
            generation_auth.append((evidence.ref.evidence_id, pre_generation))

        ledger = EvidenceLedger.from_candidates(run_id=request.run_id, evidence=tuple(candidates)).transition(
            evidence_ids=tuple(item.ref.evidence_id for item in candidates), to_stage="selected"
        )
        outcome = RetrievalOutcome(
            execution_outcome="completed",
            reason_code="evidence_retrieved",
            selected_evidence=tuple(candidates),
            ledger=ledger,
            pre_generation_authorizations=tuple(generation_auth),
            diagnostics=RetrievalDiagnostics(
                run_ref="run:" + sha256(request.run_id.encode("utf-8")).hexdigest()[:20],
                query_fingerprint=query_fingerprint(request.question, request.confirmed_conditions),
                release_identity=bundle.release_identity,
                corpus_identity=bundle.corpus_identity,
                adapter_identity="knowledge-business-rehydrate-v1",
                recipe_identity="business-active-identity-locator-v1",
                adapter_calls=0,
                authorized_entry_count=len(candidates),
                candidate_count=len(candidates),
                selected_count=len(candidates),
                elapsed_ms=round((perf_counter() - started_at) * 1000, 3),
            ),
        )
        return AcquisitionResult(
            outcome,
            {
                "runtime_kind": "business_release",
                "requirement_equivalent": True,
                "decision": "rehydrated",
                "reason": "current_identity_and_acl_confirmed",
                "old_new_relation": "unchanged_current",
            },
            self.identity,
        )

    @staticmethod
    def _empty_rehydrate_outcome(
        *,
        request: "RAGAnswerRequest",
        started_at: float,
        bundle: KnowledgeBundleView | None,
        reason_code: RetrievalReason,
        execution_outcome: RetrievalExecutionOutcome,
    ) -> RetrievalOutcome:
        """构造零泄露重水化失败；ACL deny 不允许再去检索猜测文档存在性。"""

        return RetrievalOutcome(
            execution_outcome=execution_outcome,
            reason_code=reason_code,
            selected_evidence=(),
            ledger=EvidenceLedger.from_candidates(run_id=request.run_id, evidence=()),
            pre_generation_authorizations=(),
            diagnostics=RetrievalDiagnostics(
                run_ref="run:" + sha256(request.run_id.encode("utf-8")).hexdigest()[:20],
                query_fingerprint=query_fingerprint(request.question, request.confirmed_conditions),
                release_identity=bundle.release_identity if bundle else None,
                corpus_identity=bundle.corpus_identity if bundle else None,
                adapter_identity="knowledge-business-rehydrate-v1",
                recipe_identity="business-active-identity-locator-v1",
                adapter_calls=0,
                authorized_entry_count=0,
                candidate_count=0,
                selected_count=0,
                elapsed_ms=round((perf_counter() - started_at) * 1000, 3),
            ),
        )
