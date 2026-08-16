"""M32 Knowledge Tool：把 active release 安全转换成 selected Document Evidence。

这里是文档取证的唯一控制流，但不是最终回答器。它负责 active load、ACL 双检、一次 adapter
调用、Evidence 构造和安全诊断；Evidence Gate、Composer、citation、四轴产品状态与公开 API
明确留给后续模块。这个边界能让“没召回”和“召回后回答失败”在未来分别归因。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any, Callable, Literal, Protocol

from engine.governance import (
    AuthorizationDecision,
    DocumentAuthorizationPolicy,
    TrustedCaller,
    authorize_document,
)
from engine.rag.catalog import CatalogEntry, KNOWN_PURPOSES
from engine.rag.evidence import (
    DocumentContextCoordinates,
    Evidence,
    EvidenceLedger,
    make_document_evidence,
)
from engine.rag.release import ActivePointer, ReleaseBundle, ReleaseError, load_active_release
from engine.rag.retrieval import (
    DeterministicLexicalRetrievalAdapter,
    RetrievalAdapter,
    RetrievalAdapterError,
    RetrievalBatch,
    RetrievalBudget,
    RetrievalMatch,
    query_fingerprint,
)

ExecutionOutcome = Literal["completed", "external_unavailable"]
RetrievalReason = Literal[
    "evidence_retrieved",
    "no_candidate",
    "no_authorized_evidence",
    "stale_revision",
    "active_release_unavailable",
    "retrieval_unavailable",
]
AuthorizationFn = Callable[..., AuthorizationDecision]


class KnowledgeBundleView(Protocol):
    """业务 release 与 external profile 共同满足的只读运行视图。"""

    release_identity: str
    corpus_identity: str
    authorization_policy_identity: str
    outbound_policy_identity: str
    entries: tuple[CatalogEntry, ...]


@dataclass(frozen=True)
class MaterializedDocumentContext:
    """命中 metadata entry 后，受控加载的真实 Evidence context。"""

    entry: CatalogEntry
    coordinates: DocumentContextCoordinates | None = None


ActiveLoader = Callable[[], tuple[object, KnowledgeBundleView]]
ContextLoader = Callable[[CatalogEntry], MaterializedDocumentContext]


class KnowledgeToolContractError(ValueError):
    """调用输入或 adapter 输出违反合同；正常业务零结果不抛异常。"""

    def __init__(self, reason_code: str, message: str) -> None:
        """保存稳定 reason，供测试和上层控制器失败关闭。"""

        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class KnowledgeRequest:
    """Knowledge Tool 的最小请求，不携带 HTTP request 或完整会话历史。"""

    question: str
    caller: TrustedCaller
    purpose: str
    run_id: str
    budget: RetrievalBudget = RetrievalBudget()
    confirmed_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """尽早拒绝无法形成稳定取证运行的请求。"""

        if not self.question.strip() or not self.run_id.strip():
            raise KnowledgeToolContractError("knowledge_request_invalid", "question 与 run_id 不能为空")
        if self.purpose not in KNOWN_PURPOSES:
            raise KnowledgeToolContractError("knowledge_request_invalid", "purpose 不在治理枚举中")
        if any(not condition.strip() for condition in self.confirmed_conditions):
            raise KnowledgeToolContractError("knowledge_request_invalid", "confirmed condition 不能为空")


@dataclass(frozen=True)
class RetrievalDiagnostics:
    """内部诊断记录；默认安全投影刻意省略正文、文档身份和命中数量。"""

    run_ref: str
    query_fingerprint: str
    release_identity: str | None
    corpus_identity: str | None
    adapter_identity: str
    recipe_identity: str
    adapter_calls: int
    authorized_entry_count: int
    candidate_count: int
    selected_count: int
    elapsed_ms: float

    def safe_projection(self) -> dict[str, Any]:
        """长期安全视图只证明运行身份和调用次数，不提供侧信道计数。"""

        return {
            "run_ref": self.run_ref,
            "query_fingerprint": self.query_fingerprint,
            "release_identity": self.release_identity,
            "corpus_identity": self.corpus_identity,
            "adapter_identity": self.adapter_identity,
            "recipe_identity": self.recipe_identity,
            "adapter_calls": self.adapter_calls,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True)
class RetrievalOutcome:
    """Knowledge Tool 的结构化取证事实；不包含最终 answer/safety 裁决。"""

    execution_outcome: ExecutionOutcome
    reason_code: RetrievalReason
    selected_evidence: tuple[Evidence, ...]
    ledger: EvidenceLedger
    pre_generation_authorizations: tuple[tuple[str, AuthorizationDecision], ...]
    diagnostics: RetrievalDiagnostics

    def safe_projection(self) -> dict[str, Any]:
        """返回可供长期 Trace/Eval 使用的安全投影。

        对失败统一使用 ``evidence_not_available``，避免公开层区分“库里没有”和“存在但无权”。
        技术不可用单独保留，未来 controller 才能正确投影 execution 轴。
        """

        public_reason = (
            "evidence_retrieved"
            if self.reason_code == "evidence_retrieved"
            else "retrieval_unavailable"
            if self.execution_outcome == "external_unavailable"
            else "evidence_not_available"
        )
        # ★ 内部 ledger 会保留被二次 ACL 拦下的 candidate 供同进程审计，但长期安全视图只能
        # 暴露最终 selected Evidence，否则 revision/content identity 会成为“文档存在”侧信道。
        visible_ledger = EvidenceLedger.from_candidates(
            run_id=self.ledger.run_id,
            evidence=self.selected_evidence,
        )
        if self.selected_evidence:
            visible_ledger = visible_ledger.transition(
                evidence_ids=tuple(item.ref.evidence_id for item in self.selected_evidence),
                to_stage="selected",
            )
        return {
            "execution_outcome": self.execution_outcome,
            "reason_code": public_reason,
            "selected_evidence": [item.safe_projection() for item in self.selected_evidence],
            "ledger": visible_ledger.safe_projection(),
            "diagnostics": self.diagnostics.safe_projection(),
        }


def _default_active_loader() -> tuple[ActivePointer, ReleaseBundle]:
    """窄包装默认发布入口，方便测试注入而不暴露 release 文件布局。"""

    return load_active_release()


def _default_context_loader(entry: CatalogEntry) -> MaterializedDocumentContext:
    """22 条业务知识已经内嵌全文，默认 loader 保持 M32 行为。"""

    return MaterializedDocumentContext(entry=entry)


def _run_ref(run_id: str) -> str:
    """避免 diagnostics 保存调用方提供的可读 run_id。"""

    return f"run:{sha256(run_id.encode('utf-8')).hexdigest()[:20]}"


def _empty_ledger(run_id: str) -> EvidenceLedger:
    """失败或零结果仍返回同一 typed ledger，而不是使用 ``None`` 分叉合同。"""

    return EvidenceLedger.from_candidates(run_id=run_id, evidence=())


class KnowledgeTool:
    """★ active release → ACL 双检 → retrieval → selected Evidence 的深模块。"""

    def __init__(
        self,
        *,
        adapter: RetrievalAdapter | None = None,
        active_loader: ActiveLoader = _default_active_loader,
        authorization_policy: DocumentAuthorizationPolicy | None = DocumentAuthorizationPolicy(),
        authorization_fn: AuthorizationFn = authorize_document,
        context_loader: ContextLoader = _default_context_loader,
    ) -> None:
        """注入 adapter、active loader 与授权 seam，默认只使用本地实现。"""

        self._adapter = adapter or DeterministicLexicalRetrievalAdapter()
        self._active_loader = active_loader
        self._authorization_policy = authorization_policy
        self._authorization_fn = authorization_fn
        self._context_loader = context_loader

    def retrieve(self, request: KnowledgeRequest) -> RetrievalOutcome:
        """执行一次确定性、安全取证；adapter 恰好调用一次或在 release 失败前不调用。

        多步骤顺序本身就是安全合同：未授权正文若先进入检索器，即使最终不返回，也可能通过
        远程 adapter、日志、分数或计数泄露，所以 pre-selection 必须发生在 adapter 之前。
        """

        started_at = perf_counter()
        fallback_fingerprint = query_fingerprint(request.question, request.confirmed_conditions)

        # 步骤 1：只从已校验 active release 取得运行时 corpus ============================
        try:
            _pointer, bundle = self._active_loader()
        except ReleaseError:
            return self._failure_outcome(
                request=request,
                started_at=started_at,
                reason_code="active_release_unavailable",
                execution_outcome="external_unavailable",
                query_fingerprint_value=fallback_fingerprint,
            )

        # 步骤 2：先授权、后检索；adapter 永远看不到未授权 entry ========================
        pre_selection: dict[tuple[str, str, str, str], AuthorizationDecision] = {}
        authorized_entries: list[CatalogEntry] = []
        for entry in bundle.entries:
            decision = self._authorization_fn(
                caller=request.caller,
                entry=entry,
                purpose=request.purpose,
                phase="pre_selection",
                policy=self._authorization_policy,
            )
            if decision.allowed:
                identity = (entry.document_key, entry.revision, entry.content_identity, entry.anchor)
                pre_selection[identity] = decision
                authorized_entries.append(entry)

        # 即使授权集合为空也调用一次 adapter，使一次 Tool 调用的成本/次数合同保持稳定。
        try:
            batch = self._adapter.retrieve(
                question=request.question,
                confirmed_conditions=request.confirmed_conditions,
                entries=tuple(authorized_entries),
                limit=request.budget.max_candidates,
            )
        except RetrievalAdapterError:
            return self._failure_outcome(
                request=request,
                started_at=started_at,
                reason_code="retrieval_unavailable",
                execution_outcome="external_unavailable",
                query_fingerprint_value=fallback_fingerprint,
                bundle=bundle,
                adapter_calls=1,
                authorized_entry_count=len(authorized_entries),
            )

        validated = self._validate_batch(
            batch,
            tuple(authorized_entries),
            request.budget,
            expected_query_fingerprint=fallback_fingerprint,
        )
        if not validated:
            reason: RetrievalReason = "no_authorized_evidence" if not authorized_entries else "no_candidate"
            return self._failure_outcome(
                request=request,
                started_at=started_at,
                reason_code=reason,
                execution_outcome="completed",
                query_fingerprint_value=batch.query_fingerprint,
                bundle=bundle,
                adapter_calls=1,
                authorized_entry_count=len(authorized_entries),
            )

        # 步骤 3：match identity 回到同次 bundle entry，再构造 candidate Evidence --------
        entry_index = {
            (entry.document_key, entry.revision, entry.content_identity, entry.anchor): entry
            for entry in authorized_entries
        }
        candidate_evidence: list[Evidence] = []
        entry_by_evidence: dict[str, CatalogEntry] = {}
        try:
            for match in validated:
                identity = (match.document_key, match.revision, match.content_identity, match.anchor)
                metadata_entry = entry_index[identity]
                materialized = self._context_loader(metadata_entry)
                entry = materialized.entry
                hydrated_identity = (
                    entry.document_key,
                    entry.revision,
                    entry.content_identity,
                    entry.anchor,
                )
                # ★ loader 只能补正文/坐标，不能把已授权 metadata 偷换成另一份 unit。
                if hydrated_identity != identity or not entry.content.strip():
                    raise RetrievalAdapterError(
                        "retrieval_context_invalid", "context loader 返回未知或空 unit"
                    )
                evidence = make_document_evidence(
                    run_id=request.run_id,
                    release_identity=bundle.release_identity,
                    entry=entry,
                    purpose=request.purpose,
                    authorization=pre_selection[identity],
                    runtime_ref=f"retrieval:{batch.adapter_identity}:{batch.recipe_identity}",
                    context_coordinates=materialized.coordinates,
                )
                candidate_evidence.append(evidence)
                entry_by_evidence[evidence.ref.evidence_id] = entry
        except (OSError, RetrievalAdapterError):
            return self._failure_outcome(
                request=request,
                started_at=started_at,
                reason_code="retrieval_unavailable",
                execution_outcome="external_unavailable",
                query_fingerprint_value=batch.query_fingerprint,
                bundle=bundle,
                adapter_calls=1,
                authorized_entry_count=len(authorized_entries),
            )

        ledger = EvidenceLedger.from_candidates(run_id=request.run_id, evidence=tuple(candidate_evidence))
        provisional_ids = tuple(
            evidence.ref.evidence_id
            for evidence in candidate_evidence[: request.budget.max_selected]
        )

        # 步骤 4：选中后再次授权；通过也只推进 selected，不冒充真实入模 ==============
        selected_ids: list[str] = []
        generation_decisions: list[tuple[str, AuthorizationDecision]] = []
        denied_reasons: list[str] = []
        for evidence_id in provisional_ids:
            entry = entry_by_evidence[evidence_id]
            decision = self._authorization_fn(
                caller=request.caller,
                entry=entry,
                purpose=request.purpose,
                phase="pre_generation",
                policy=self._authorization_policy,
            )
            if decision.allowed:
                selected_ids.append(evidence_id)
                generation_decisions.append((evidence_id, decision))
            else:
                denied_reasons.append(decision.reason_code)

        if not selected_ids:
            reason = "stale_revision" if "revision_unavailable" in denied_reasons else "no_authorized_evidence"
            return self._failure_outcome(
                request=request,
                started_at=started_at,
                reason_code=reason,
                execution_outcome="completed",
                query_fingerprint_value=batch.query_fingerprint,
                bundle=bundle,
                adapter_calls=1,
                authorized_entry_count=len(authorized_entries),
                candidate_count=len(candidate_evidence),
                ledger=ledger,
            )

        ledger = ledger.transition(evidence_ids=tuple(selected_ids), to_stage="selected")
        selected_set = set(selected_ids)
        selected = tuple(item for item in candidate_evidence if item.ref.evidence_id in selected_set)
        diagnostics = self._diagnostics(
            request=request,
            started_at=started_at,
            query_fingerprint_value=batch.query_fingerprint,
            bundle=bundle,
            adapter_calls=1,
            authorized_entry_count=len(authorized_entries),
            candidate_count=len(candidate_evidence),
            selected_count=len(selected),
        )
        return RetrievalOutcome(
            execution_outcome="completed",
            reason_code="evidence_retrieved",
            selected_evidence=selected,
            ledger=ledger,
            pre_generation_authorizations=tuple(generation_decisions),
            diagnostics=diagnostics,
        )

    def _validate_batch(
        self,
        batch: RetrievalBatch,
        entries: tuple[CatalogEntry, ...],
        budget: RetrievalBudget,
        *,
        expected_query_fingerprint: str,
    ) -> tuple[RetrievalMatch, ...]:
        """拒绝 adapter 越权引用、重复、超预算、乱 rank 或非法 score。"""

        if batch.adapter_identity != self._adapter.identity or batch.recipe_identity != self._adapter.recipe_identity:
            raise KnowledgeToolContractError("retrieval_runtime_mismatch", "adapter 返回的 runtime identity 不一致")
        if batch.query_fingerprint != expected_query_fingerprint:
            raise KnowledgeToolContractError("retrieval_query_mismatch", "adapter 返回的 query identity 不一致")
        if len(batch.matches) > budget.max_candidates:
            raise KnowledgeToolContractError("retrieval_budget_exceeded", "adapter 返回候选数超过预算")

        allowed = {
            (entry.document_key, entry.revision, entry.content_identity, entry.anchor)
            for entry in entries
        }
        seen: set[tuple[str, str, str, str]] = set()
        for expected_rank, match in enumerate(batch.matches, start=1):
            identity = (match.document_key, match.revision, match.content_identity, match.anchor)
            if identity not in allowed:
                raise KnowledgeToolContractError("retrieval_unknown_entry", "adapter 返回了输入集合外的 entry")
            if identity in seen:
                raise KnowledgeToolContractError("retrieval_match_duplicate", "adapter 返回重复 entry identity")
            if match.rank != expected_rank or not math_is_finite_positive(match.score):
                raise KnowledgeToolContractError("retrieval_match_invalid", "adapter rank/score 非法")
            seen.add(identity)
        return batch.matches

    def _failure_outcome(
        self,
        *,
        request: KnowledgeRequest,
        started_at: float,
        reason_code: RetrievalReason,
        execution_outcome: ExecutionOutcome,
        query_fingerprint_value: str,
        bundle: KnowledgeBundleView | None = None,
        adapter_calls: int = 0,
        authorized_entry_count: int = 0,
        candidate_count: int = 0,
        ledger: EvidenceLedger | None = None,
    ) -> RetrievalOutcome:
        """统一构造失败/零结果，保证不同路径不会漏掉 runtime identity。"""

        diagnostics = self._diagnostics(
            request=request,
            started_at=started_at,
            query_fingerprint_value=query_fingerprint_value,
            bundle=bundle,
            adapter_calls=adapter_calls,
            authorized_entry_count=authorized_entry_count,
            candidate_count=candidate_count,
            selected_count=0,
        )
        return RetrievalOutcome(
            execution_outcome=execution_outcome,
            reason_code=reason_code,
            selected_evidence=(),
            ledger=ledger or _empty_ledger(request.run_id),
            pre_generation_authorizations=(),
            diagnostics=diagnostics,
        )

    def _diagnostics(
        self,
        *,
        request: KnowledgeRequest,
        started_at: float,
        query_fingerprint_value: str,
        bundle: KnowledgeBundleView | None,
        adapter_calls: int,
        authorized_entry_count: int,
        candidate_count: int,
        selected_count: int,
    ) -> RetrievalDiagnostics:
        """集中建立 diagnostics，避免错误分支出现字段缺失或语义漂移。"""

        return RetrievalDiagnostics(
            run_ref=_run_ref(request.run_id),
            query_fingerprint=query_fingerprint_value,
            release_identity=bundle.release_identity if bundle else None,
            corpus_identity=bundle.corpus_identity if bundle else None,
            adapter_identity=self._adapter.identity,
            recipe_identity=self._adapter.recipe_identity,
            adapter_calls=adapter_calls,
            authorized_entry_count=authorized_entry_count,
            candidate_count=candidate_count,
            selected_count=selected_count,
            elapsed_ms=round((perf_counter() - started_at) * 1000, 3),
        )


def math_is_finite_positive(value: float) -> bool:
    """避免 NaN/inf 或非正分数破坏排序与 artifact JSON identity。"""

    try:
        return value > 0 and value < float("inf")
    except TypeError:
        return False
