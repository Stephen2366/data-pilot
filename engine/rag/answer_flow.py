"""M33 可信 RAG 回答闭环，以及 M37 业务 Document Evidence 窄重水化。

本模块对 P3 只暴露一个 :class:`RAGAnswerFlow` 深 interface。调用者提交问题、可信 caller
和结构化 Evidence requirement 后，模块内部依次调用 M32 Knowledge Tool、执行回答 Gate、
构造真正的 generation context、生成确定性 claim、校验 citation，最后返回四轴结果。

★ 这里刻意不接 HTTP、LangGraph 或远程模型。这样 P3 只需要决定“何时调用 RAG”，不用
重新理解 Evidence 阶段、引用校验和失败投影，也不会把请求体 ``user_role`` 错当可信身份。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any, Callable, Literal, Mapping

from engine.governance import (
    DOCUMENT_AUTHORIZATION_POLICY_IDENTITY,
    OUTBOUND_POLICY_IDENTITY,
    AuthorizationDecision,
    TrustedCaller,
    authorize_document,
    document_safe_ref,
)
from engine.rag.catalog import CatalogEntry, KNOWN_PURPOSES
from engine.rag.evidence import (
    CitationDraft,
    CitationSlot,
    DocumentEvidencePayload,
    Evidence,
    EvidenceContractError,
    EvidenceLedger,
    EvidenceRef,
    ValidatedCitation,
    allocate_citation_slot,
    validate_citations,
    make_document_evidence,
)
from engine.rag.knowledge_tool import (
    ExecutionOutcome as RetrievalExecutionOutcome,
    KnowledgeBundleView,
    KnowledgeRequest,
    KnowledgeTool,
    RetrievalOutcome,
    RetrievalDiagnostics,
    RetrievalReason,
)
from engine.rag.release import ActivePointer, ReleaseBundle, ReleaseError, load_active_release
from engine.rag.retrieval import RetrievalBudget, query_fingerprint

RouteStatus = Literal["rag"]
ExecutionStatus = Literal["completed", "external_unavailable", "failed"]
AnswerStatus = Literal["complete", "insufficient_evidence", "no_answer"]
SafetyStatus = Literal["passed", "blocked"]
GateReason = Literal[
    "answer_allowed",
    "evidence_insufficient",
    "document_revision_inactive",
    "document_acl_denied",
    "document_instruction_blocked",
]
AnswerReason = Literal[
    "answer_completed",
    "evidence_no_candidate",
    "evidence_insufficient",
    "document_revision_inactive",
    "document_acl_denied",
    "document_instruction_blocked",
    "retrieval_unavailable",
    "active_release_unavailable",
    "composer_unavailable",
    "citation_invalid",
]
ActiveLoader = Callable[[], tuple[object, KnowledgeBundleView]]

DETERMINISTIC_COMPOSER_IDENTITY = "rag-deterministic-evidence-composer-v1"
ANSWER_FLOW_RUNTIME_IDENTITY = "rag-answer-flow-local-v1"

# 文档正文是不可信数据。首版 deterministic Composer 不执行文本，但也不能把明显的伪系统、
# 伪 Tool/citation 指令原样展示给用户。这里只冻结“命中即保守阻断”的安全语义，不把具体
# pattern 当长期检索/模型参数；未来调整必须更新 runtime identity 和安全回归。
_INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"忽略(?:之前|以上|所有)?(?:的)?(?:系统)?指令",
        r"伪造\s*citation",
        r"调用\s*(?:sql\s*)?tool",
        r"<\s*tool[_ -]?call",
        r"system\s*prompt",
    )
)


class AnswerFlowContractError(ValueError):
    """输入或内部返回值违反 M33 合同；正常业务失败使用四轴结果表达。"""

    def __init__(self, reason_code: str, message: str) -> None:
        """保留稳定 reason，避免调用者解析异常文案。"""

        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


class ComposerUnavailableError(RuntimeError):
    """确定性 Composer 的可注入技术失败；与空 Evidence 或安全拒绝不同。"""

    def __init__(self, message: str = "composer unavailable") -> None:
        """错误正文只供本地调试，绝不进入公开 answer。"""

        super().__init__(message)


def _hash(namespace: str, *parts: str) -> str:
    """使用规范分隔生成本轮 context/claim/runtime reference。"""

    payload = "\0".join((namespace, *parts)).encode("utf-8")
    return f"{namespace}:{sha256(payload).hexdigest()}"


def _normalize(value: str) -> str:
    """NFKC + 小写 + 去空白，服务本地保守的 required term 判断。"""

    return "".join(unicodedata.normalize("NFKC", value).lower().split())


def _required_unique_texts(name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    """拒绝空值和重复 requirement，避免同一条件被伪装成多项满足。"""

    normalized = tuple(item.strip() for item in values)
    if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
        raise AnswerFlowContractError("answer_requirement_invalid", f"{name} 包含空值或重复值")
    return normalized


@dataclass(frozen=True)
class AnswerEvidenceRequirement:
    """Gate 可确定性验证的最小 Evidence requirement。

    ``required_terms`` 只适合首批结构化政策/指标事实，用于证明“候选存在但不足以支持某个
    具体事实”可以与 zero-hit 分开。它不是开放语义 Judge，也不能由 HTTP 用户直接指定。
    P3 后续只能从受控 Router/controller 生成此对象。
    """

    min_evidence: int = 1
    required_document_keys: tuple[str, ...] = ()
    required_knowledge_types: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    max_claims: int = 3

    def __post_init__(self) -> None:
        """在取证前拒绝无意义、倒挂或会污染 Gate 的 requirement。"""

        if self.min_evidence < 1 or self.max_claims < 1 or self.min_evidence > self.max_claims:
            raise AnswerFlowContractError(
                "answer_requirement_invalid", "min_evidence/max_claims 必须为正且不能倒挂"
            )
        for name in ("required_document_keys", "required_knowledge_types", "required_terms"):
            _required_unique_texts(name, getattr(self, name))

    @property
    def identity(self) -> str:
        """让 requirement 进入 runtime/Eval identity，而不保存原始问题。"""

        return _hash(
            "answer-requirement",
            str(self.min_evidence),
            "|".join(self.required_document_keys),
            "|".join(self.required_knowledge_types),
            "|".join(self.required_terms),
            str(self.max_claims),
        )


@dataclass(frozen=True)
class RAGAnswerRequest:
    """AnswerFlow 的唯一请求，不携带 HTTP、Graph state 或完整历史。"""

    question: str
    caller: TrustedCaller
    run_id: str
    purpose: str = "answer_evidence"
    requirement: AnswerEvidenceRequirement = AnswerEvidenceRequirement()
    retrieval_budget: RetrievalBudget = RetrievalBudget()
    confirmed_conditions: tuple[str, ...] = ()
    knowledge_runtime_kind: Literal["business_release", "external_profile"] = "business_release"
    prior_evidence_refs: tuple[EvidenceRef, ...] = ()
    requirement_equivalent: bool = False

    def __post_init__(self) -> None:
        """保证本轮可以形成稳定 KnowledgeRequest 和 Evidence identity。"""

        if not self.question.strip() or not self.run_id.strip() or self.purpose not in KNOWN_PURPOSES:
            raise AnswerFlowContractError("answer_request_invalid", "question/run_id/purpose 非法")
        _required_unique_texts("confirmed_conditions", self.confirmed_conditions)
        if self.knowledge_runtime_kind not in {"business_release", "external_profile"}:
            raise AnswerFlowContractError("answer_request_invalid", "knowledge runtime kind 未登记")
        if self.requirement_equivalent and not self.prior_evidence_refs:
            raise AnswerFlowContractError("answer_request_invalid", "等价复用必须携带旧 EvidenceRef")


@dataclass(frozen=True)
class GenerationContext:
    """Composer 真正看见的 typed Evidence context；完整对象仅在受控进程内使用。"""

    run_id: str
    context_identity: str
    requirement_identity: str
    release_identity: str
    evidence: tuple[Evidence, ...]

    def safe_projection(self) -> dict[str, Any]:
        """长期投影只证明真实入模 identity，不保存正文。"""

        return {
            "context_identity": self.context_identity,
            "requirement_identity": self.requirement_identity,
            "release_identity": self.release_identity,
            "evidence": [item.safe_projection() for item in self.evidence],
        }


@dataclass(frozen=True)
class GateDecision:
    """Shared Answer Evidence Gate 的稳定决定和安全检查事实。"""

    allowed: bool
    reason_code: GateReason
    ledger: EvidenceLedger
    context: GenerationContext | None
    checks: tuple[str, ...]

    def safe_projection(self) -> dict[str, Any]:
        """不把被拒文档 identity、正文或 ACL 内部原因放入长期投影。"""

        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "context": self.context.safe_projection() if self.context is not None else None,
            "checks": list(self.checks),
        }


@dataclass(frozen=True)
class ClaimDraft:
    """Composer 的结构化草稿；自然语言结论和逐字证据片段必须分开。

    ``text`` 是最终给用户看的表述，可以是对原文的忠实改写；``support_text`` 则是
    Composer 声称支持该结论的原文片段。后者必须能被代码在绑定 Evidence 中逐字找到。
    ★ 字符串校验只能证明“证据真的存在”，不能自动证明改写与证据在语义上等价。
    """

    text: str
    support_text: str
    evidence_id: str
    anchor: str


@dataclass(frozen=True)
class ValidatedClaim:
    """只在 citation 全量通过后才可进入最终 answer 的 claim。"""

    claim_ref: str
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class UserCitation:
    """用户可回查的最小 citation 视图；不包含正文、score 或 ACL 细节。"""

    citation_id: str
    claim_ref: str
    title: str
    revision: str
    anchor: str
    authority_ref: str

    def docs_used_projection(self) -> dict[str, str]:
        """G0 兼容视图只能由 validated citation 单向派生。"""

        return {
            "citation_id": self.citation_id,
            "title": self.title,
            "revision": self.revision,
            "anchor": self.anchor,
        }


@dataclass(frozen=True)
class AnswerFlowDiagnostics:
    """一次流程的有界调用/耗时/runtime 事实，不保存 question 或正文。"""

    runtime_identity: str
    composer_identity: str
    release_identity: str | None
    corpus_identity: str | None
    retrieval_adapter_identity: str
    retrieval_recipe_identity: str
    authorization_policy_identity: str
    outbound_policy_identity: str
    knowledge_tool_calls: int
    gate_calls: int
    composer_calls: int
    validator_calls: int
    context_count: int
    context_characters: int
    elapsed_ms: float

    def safe_projection(self) -> dict[str, Any]:
        """返回 Eval/Trace 可消费的白名单字段。"""

        return asdict(self)


@dataclass(frozen=True)
class RAGAnswerResult:
    """一次内部 RAG 回答运行的完整四轴事实。"""

    route_status: RouteStatus
    execution_status: ExecutionStatus
    answer_status: AnswerStatus
    safety_status: SafetyStatus
    reason_code: AnswerReason
    answer: str | None
    claims: tuple[ValidatedClaim, ...]
    citations: tuple[UserCitation, ...]
    ledger: EvidenceLedger
    gate_decision: GateDecision | None
    retrieval_reason: str
    diagnostics: AnswerFlowDiagnostics
    evidence_validity: Mapping[str, Any]

    @property
    def docs_used(self) -> tuple[dict[str, str], ...]:
        """旧兼容字段不是事实源，只读 validated citations。"""

        return tuple(item.docs_used_projection() for item in self.citations)

    def safe_projection(self) -> dict[str, Any]:
        """形成未来 AgentResponse 可复用的安全投影。"""

        # ★ 失败时内部 ledger 仍要保留，供本地审计“在哪一步被挡住”；但公开投影不能借此
        # 暴露某份无权文档/污染文档是否存在。只有完整通过 citation validator 的回答，才
        # 公开最终 cited Evidence refs。这样安全投影和内部审计账本各司其职。
        completed = self.answer_status == "complete" and self.safety_status == "passed"
        public_ledger = self.ledger.safe_projection() if completed else EvidenceLedger(run_id=self.ledger.run_id).safe_projection()
        if self.gate_decision is None:
            public_gate = None
        else:
            public_gate = {
                "allowed": self.gate_decision.allowed,
                "reason_code": _public_reason(self.reason_code),
                "context": self.gate_decision.context.safe_projection() if completed and self.gate_decision.context else None,
                "checks": list(self.gate_decision.checks) if completed else [],
            }

        return {
            "route_status": self.route_status,
            "execution_status": self.execution_status,
            "answer_status": self.answer_status,
            "safety_status": self.safety_status,
            "reason_code": _public_reason(self.reason_code),
            "answer": self.answer,
            "claims": [asdict(item) for item in self.claims],
            "citations": [asdict(item) for item in self.citations],
            "docs_used": list(self.docs_used),
            "ledger": public_ledger,
            "gate": public_gate,
            "diagnostics": self.diagnostics.safe_projection(),
            "evidence_validity": dict(self.evidence_validity),
        }


@dataclass(frozen=True)
class RAGPreparedEvidence:
    """Hybrid 专用的 RAG 深链输出：只完成 retrieval + Shared Gate。

    ★ 这不是第二个 AnswerFlow。它复用同一份 Knowledge Tool、active release 与 Gate，把
    ``generation_visible`` 的 Document Evidence 交给上层唯一 Hybrid Synthesizer；因此不会先
    生成一个 RAG 子答案，再让另一个组件把两个自然语言答案拼接起来。
    """

    result: RAGAnswerResult | None
    gate: GateDecision | None
    diagnostics: AnswerFlowDiagnostics
    evidence_validity: Mapping[str, Any]

    @property
    def available(self) -> bool:
        """只有 Gate 允许且生成上下文存在时，Document Evidence 才能离开 RAG 深链。"""

        return self.result is None and self.gate is not None and self.gate.allowed and self.gate.context is not None


def _public_reason(reason: AnswerReason) -> str:
    """把内部精确 root cause 收敛为不会暴露文档存在性的公开 reason。"""

    if reason == "answer_completed":
        return "completed"
    if reason in {"evidence_no_candidate", "evidence_insufficient", "document_revision_inactive"}:
        return "insufficient_evidence"
    if reason == "document_acl_denied":
        return "access_not_available"
    if reason == "document_instruction_blocked":
        return "content_not_usable"
    if reason == "citation_invalid":
        return "answer_validation_failed"
    return "processing_not_available"


def _default_active_loader() -> tuple[ActivePointer, ReleaseBundle]:
    """保持 release 文件布局在 AnswerFlow interface 之外。"""

    return load_active_release()


def _bundle_entry_index(
    bundle: KnowledgeBundleView,
) -> Mapping[tuple[str, str], CatalogEntry]:
    """优先复用大 profile 的只读索引；旧 22 条 release 仍可现场建立小字典。"""

    supplied = getattr(bundle, "entry_index", None)
    if supplied is not None:
        return supplied
    return {(entry.document_key, entry.revision): entry for entry in bundle.entries}


def _strip_markdown_heading(content: str) -> str:
    """删除首个 Markdown 标题，保留原件正文作为确定性 extractive claim。"""

    lines = content.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    return "\n\n".join(line.strip() for line in lines if line.strip())


class DeterministicEvidenceComposer:
    """首个本地 Composer implementation：每份 Evidence 形成一个原文绑定 claim。

    它不做开放改写，也不声称语言质量最优；价值在于让 M33 能确定性证明“实际入模内容、
    claim support 与 citation identity 是同一份 Evidence”。未来远程 Composer 必须另过出站
    决策和效果证据门，不能静默替换此 runtime identity。
    """

    identity = DETERMINISTIC_COMPOSER_IDENTITY

    def compose(
        self,
        *,
        context: GenerationContext,
        question: str,
        confirmed_conditions: tuple[str, ...],
        max_claims: int,
    ) -> tuple[ClaimDraft, ...]:
        """按 context 顺序生成有界 extractive claims。"""

        if not question.strip() or max_claims < 1 or len(context.evidence) > max_claims:
            raise AnswerFlowContractError("composer_budget_invalid", "generation context 超过 claim 预算")
        _required_unique_texts("confirmed_conditions", confirmed_conditions)
        drafts: list[ClaimDraft] = []
        for evidence in context.evidence:
            if not isinstance(evidence.payload, DocumentEvidencePayload):
                raise AnswerFlowContractError("composer_evidence_invalid", "RAG Composer 只接受 Document Evidence")
            text = _strip_markdown_heading(evidence.payload.content)
            if not text:
                raise AnswerFlowContractError("composer_output_invalid", "Document Evidence 没有可展示正文")
            # M37 的两个解释样式仍是 deterministic presentation，不让模型自由改写事实。
            # support_text 始终保持原文，后续 citation validator 因而仍校验同一份 Evidence。
            if question.startswith("请用通俗说明解释同一条规则"):
                text = f"通俗说明：{text}"
            elif question.startswith("请用分步说明解释同一条规则"):
                paragraphs = [item.strip() for item in text.split("\n\n") if item.strip()]
                text = "分步说明：\n" + "\n".join(
                    f"{index}. {paragraph}" for index, paragraph in enumerate(paragraphs, start=1)
                )
            drafts.append(
                ClaimDraft(
                    text=text,
                    # 本地 baseline 不做改写，直接把整份实际入模正文作为可回查 support。
                    support_text=evidence.payload.content,
                    evidence_id=evidence.ref.evidence_id,
                    anchor=evidence.ref.anchor,
                )
            )
        if not drafts:
            raise AnswerFlowContractError("composer_output_invalid", "Composer 不允许返回空 claim 集")
        return tuple(drafts)


class RAGAnswerFlow:
    """★ P3 可直接调用的可信 RAG 回答深 module。"""

    def __init__(
        self,
        *,
        knowledge_tool: KnowledgeTool | None = None,
        composer: DeterministicEvidenceComposer | None = None,
        active_loader: ActiveLoader = _default_active_loader,
    ) -> None:
        """注入本地依赖便于故障测试；外部调用者仍只使用 ``run`` interface。"""

        self._knowledge_tool = knowledge_tool or KnowledgeTool()
        self._composer = composer or DeterministicEvidenceComposer()
        self._active_loader = active_loader

    def run(self, request: RAGAnswerRequest) -> RAGAnswerResult:
        """★ 执行一次取证、Gate、Composer、citation 和四轴投影。

        步骤顺序是合同的一部分。特别是 ``generation_visible`` 只能在 Gate 已形成最小 context、
        且马上要调用 Composer 时推进；validator 失败后保留该审计事实，但绝不公开草稿答案。
        """

        started_at = perf_counter()
        tool_calls = gate_calls = composer_calls = validator_calls = 0

        # 步骤 1：follow-up 先裁决旧 Evidence；普通/SQL 无关请求仍走原 M32 深 module。====
        outcome, validity = self._obtain_evidence(request, started_at=started_at)
        tool_calls = 0 if validity.get("decision") in {"rehydrated", "denied", "unavailable"} else 1
        early = self._from_retrieval_failure(
            request=request,
            outcome=outcome,
            started_at=started_at,
            counts=(tool_calls, gate_calls, composer_calls, validator_calls),
            evidence_validity=validity,
        )
        if early is not None:
            return early

        # 步骤 2：重新加载当前 active release，避免检索后 revision/ACL 漂移 -------------
        try:
            _pointer, bundle = self._active_loader()
        except ReleaseError:
            return self._failure_result(
                outcome=outcome,
                execution_status="external_unavailable",
                answer_status="no_answer",
                safety_status="passed",
                reason_code="active_release_unavailable",
                gate_decision=None,
                started_at=started_at,
                counts=(tool_calls, gate_calls, composer_calls, validator_calls),
                evidence_validity=validity,
            )
        current_entries = _bundle_entry_index(bundle)

        # 步骤 3：Shared Gate 形成真实 generation context 并推进 ledger ================
        gate_calls += 1
        gate = self._gate(
            request=request,
            outcome=outcome,
            bundle=bundle,
            current_entries=current_entries,
        )
        if not gate.allowed:
            return self._from_gate_denial(
                outcome=outcome,
                gate=gate,
                bundle=bundle,
                started_at=started_at,
                counts=(tool_calls, gate_calls, composer_calls, validator_calls),
                evidence_validity=validity,
            )
        if gate.context is None:
            raise AnswerFlowContractError("gate_output_invalid", "allow decision 必须携带 generation context")

        # 步骤 4：Composer 只看 Gate context；异常不回显正文或错误文本 -----------------
        composer_calls += 1
        try:
            drafts = self._composer.compose(
                context=gate.context,
                question=request.question,
                confirmed_conditions=request.confirmed_conditions,
                max_claims=request.requirement.max_claims,
            )
        except ComposerUnavailableError:
            return self._failure_result(
                outcome=outcome,
                execution_status="failed",
                answer_status="no_answer",
                safety_status="passed",
                reason_code="composer_unavailable",
                gate_decision=gate,
                started_at=started_at,
                counts=(tool_calls, gate_calls, composer_calls, validator_calls),
                bundle=bundle,
                evidence_validity=validity,
            )
        self._validate_claim_drafts(drafts=drafts, context=gate.context, max_claims=request.requirement.max_claims)

        # 步骤 5：代码分配 claim/slot，再由现有 validator 全量校验 =====================
        slots, citation_drafts, claim_refs = self._build_citation_drafts(
            run_id=request.run_id,
            drafts=drafts,
        )
        validator_calls += 1
        try:
            validated, cited_ledger = validate_citations(
                ledger=gate.ledger,
                slots=slots,
                drafts=citation_drafts,
                current_entries=current_entries,
                generation_authorizations=dict(outcome.pre_generation_authorizations),
            )
            self._validate_complete_citation_set(slots=slots, citations=validated)
        except EvidenceContractError:
            return self._failure_result(
                outcome=outcome,
                execution_status="completed",
                answer_status="no_answer",
                safety_status="blocked",
                reason_code="citation_invalid",
                gate_decision=gate,
                started_at=started_at,
                counts=(tool_calls, gate_calls, composer_calls, validator_calls),
                bundle=bundle,
                evidence_validity=validity,
            )

        claims, citations = self._validated_output(
            drafts=drafts,
            claim_refs=claim_refs,
            validated=validated,
            ledger=cited_ledger,
            current_entries=current_entries,
        )
        answer = "\n\n".join(item.text for item in claims)
        return RAGAnswerResult(
            route_status="rag",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="answer_completed",
            answer=answer,
            claims=claims,
            citations=citations,
            ledger=cited_ledger,
            gate_decision=gate,
            retrieval_reason=outcome.reason_code,
            diagnostics=self._diagnostics(
                outcome=outcome,
                started_at=started_at,
                counts=(tool_calls, gate_calls, composer_calls, validator_calls),
                bundle=bundle,
                context=gate.context,
            ),
            evidence_validity=validity,
        )

    def prepare_for_hybrid(self, request: RAGAnswerRequest) -> RAGPreparedEvidence:
        """执行 Hybrid RAG branch 到 Shared Gate 为止，不调用 Composer 或 citation validator。

        这里复用 ``run`` 前半段而不是由 Harness 自己调用私有 Gate：RAG 仍独占 release 重载、
        ACL 双检和 Evidence stage 迁移。成功时 controller 只会得到 Gate 明确允许的 context；
        失败时返回既有四轴结果，且不会产生任何可被当成答案的自然语言子结果。
        """

        started_at = perf_counter()
        tool_calls = gate_calls = 0
        outcome, validity = self._obtain_evidence(request, started_at=started_at)
        tool_calls = 0 if validity.get("decision") in {"rehydrated", "denied", "unavailable"} else 1
        early = self._from_retrieval_failure(
            request=request,
            outcome=outcome,
            started_at=started_at,
            counts=(tool_calls, gate_calls, 0, 0),
            evidence_validity=validity,
        )
        if early is not None:
            return RAGPreparedEvidence(
                result=early,
                gate=None,
                diagnostics=early.diagnostics,
                evidence_validity=validity,
            )

        try:
            _pointer, bundle = self._active_loader()
        except ReleaseError:
            failed = self._failure_result(
                outcome=outcome,
                execution_status="external_unavailable",
                answer_status="no_answer",
                safety_status="passed",
                reason_code="active_release_unavailable",
                gate_decision=None,
                started_at=started_at,
                counts=(tool_calls, gate_calls, 0, 0),
                evidence_validity=validity,
            )
            return RAGPreparedEvidence(
                result=failed,
                gate=None,
                diagnostics=failed.diagnostics,
                evidence_validity=validity,
            )

        gate_calls = 1
        gate = self._gate(
            request=request,
            outcome=outcome,
            bundle=bundle,
            current_entries=_bundle_entry_index(bundle),
        )
        if not gate.allowed or gate.context is None:
            failed = self._from_gate_denial(
                outcome=outcome,
                gate=gate,
                bundle=bundle,
                started_at=started_at,
                counts=(tool_calls, gate_calls, 0, 0),
                evidence_validity=validity,
            )
            return RAGPreparedEvidence(
                result=failed,
                gate=gate,
                diagnostics=failed.diagnostics,
                evidence_validity=validity,
            )

        diagnostics = self._diagnostics(
            outcome=outcome,
            started_at=started_at,
            counts=(tool_calls, gate_calls, 0, 0),
            bundle=bundle,
            context=gate.context,
        )
        return RAGPreparedEvidence(
            result=None,
            gate=gate,
            diagnostics=diagnostics,
            evidence_validity=validity,
        )

    def _obtain_evidence(
        self,
        request: RAGAnswerRequest,
        *,
        started_at: float,
    ) -> tuple[RetrievalOutcome, dict[str, Any]]:
        """执行 M37 窄 B：仅业务 release 的等价 action 可跳过 retrieval。"""

        def retrieve(reason: str) -> tuple[RetrievalOutcome, dict[str, Any]]:
            """统一执行至多一次 Knowledge Tool，并记录为什么必须重新取证。"""

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
            return outcome, {
                "runtime_kind": request.knowledge_runtime_kind,
                "requirement_equivalent": request.requirement_equivalent,
                "decision": "reacquired",
                "reason": reason,
                "old_new_relation": "not_comparable",
            }

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
            outcome = self._empty_rehydrate_outcome(
                request=request,
                started_at=started_at,
                bundle=None,
                reason_code="active_release_unavailable",
                execution_outcome="external_unavailable",
            )
            return outcome, {
                "runtime_kind": "business_release",
                "requirement_equivalent": True,
                "decision": "unavailable",
                "reason": "active_release_unavailable",
                "old_new_relation": "unavailable",
            }

        current_entries = tuple(bundle.entries)
        located: list[CatalogEntry] = []
        for ref in request.prior_evidence_refs:
            matches = [
                entry
                for entry in current_entries
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
                caller=request.caller,
                entry=entry,
                purpose=request.purpose,
                phase="pre_selection",
            )
            if not pre_selection.allowed:
                outcome = self._empty_rehydrate_outcome(
                    request=request,
                    started_at=started_at,
                    bundle=bundle,
                    reason_code="no_authorized_evidence",
                    execution_outcome="completed",
                )
                return outcome, {
                    "runtime_kind": "business_release",
                    "requirement_equivalent": True,
                    "decision": "denied",
                    "reason": "reauthorization_denied",
                    "old_new_relation": "undisclosed",
                }
            evidence = make_document_evidence(
                run_id=request.run_id,
                release_identity=bundle.release_identity,
                entry=entry,
                purpose=request.purpose,
                authorization=pre_selection,
                runtime_ref="rehydrate:business-active-identity-v1",
            )
            pre_generation = authorize_document(
                caller=request.caller,
                entry=entry,
                purpose=request.purpose,
                phase="pre_generation",
            )
            if not pre_generation.allowed:
                outcome = self._empty_rehydrate_outcome(
                    request=request,
                    started_at=started_at,
                    bundle=bundle,
                    reason_code="no_authorized_evidence",
                    execution_outcome="completed",
                )
                return outcome, {
                    "runtime_kind": "business_release",
                    "requirement_equivalent": True,
                    "decision": "denied",
                    "reason": "reauthorization_denied",
                    "old_new_relation": "undisclosed",
                }
            candidates.append(evidence)
            generation_auth.append((evidence.ref.evidence_id, pre_generation))

        ledger = EvidenceLedger.from_candidates(run_id=request.run_id, evidence=tuple(candidates))
        ledger = ledger.transition(
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
        return outcome, {
            "runtime_kind": "business_release",
            "requirement_equivalent": True,
            "decision": "rehydrated",
            "reason": "current_identity_and_acl_confirmed",
            "old_new_relation": "unchanged_current",
        }

    @staticmethod
    def _empty_rehydrate_outcome(
        *,
        request: RAGAnswerRequest,
        started_at: float,
        bundle: KnowledgeBundleView | None,
        reason_code: RetrievalReason,
        execution_outcome: RetrievalExecutionOutcome,
    ) -> RetrievalOutcome:
        """构造零泄露重水化失败；ACL deny 不允许转去 retrieval 猜测文档存在性。"""

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

    def _gate(
        self,
        *,
        request: RAGAnswerRequest,
        outcome: RetrievalOutcome,
        bundle: KnowledgeBundleView,
        current_entries: Mapping[tuple[str, str], CatalogEntry],
    ) -> GateDecision:
        """验证 selected/current/auth/requirement，构造最小 context 并真实推进阶段。"""

        selected = outcome.selected_evidence
        selected_ids = tuple(item.ref.evidence_id for item in selected)
        auth_map = dict(outcome.pre_generation_authorizations)
        entry_map = current_entries

        if not selected or set(auth_map) != set(selected_ids):
            return GateDecision(False, "document_acl_denied", outcome.ledger, None, ("authorization_complete",))

        eligible: list[Evidence] = []
        for item in selected:
            if item.ref.run_id != request.run_id or outcome.ledger.stage_of(item.ref.evidence_id) != "selected":
                raise AnswerFlowContractError("gate_evidence_invalid", "selected Evidence 的 run/stage 不一致")
            if request.purpose not in item.allowed_uses or not isinstance(item.payload, DocumentEvidencePayload):
                raise AnswerFlowContractError("gate_evidence_invalid", "Evidence kind/purpose 不符合 RAG 回答合同")
            payload = item.payload
            current = entry_map.get((payload.document_key, payload.revision))
            if (
                current is None
                or current.status != "active"
                or bundle.release_identity != payload.release_identity
                or bundle.release_identity != outcome.diagnostics.release_identity
                or current.content_identity != item.ref.content_identity
                or current.anchor != item.ref.anchor
                or current.authority_ref != item.ref.authority_identity
            ):
                return GateDecision(
                    False,
                    "document_revision_inactive",
                    outcome.ledger,
                    None,
                    ("current_revision",),
                )
            decision = auth_map[item.ref.evidence_id]
            if (
                not decision.allowed
                or decision.phase != "pre_generation"
                or decision.allowed_purpose != request.purpose
                or decision.caller_safe_ref != request.caller.audit_ref
                or decision.evidence_safe_ref != document_safe_ref(current)
            ):
                return GateDecision(
                    False,
                    "document_acl_denied",
                    outcome.ledger,
                    None,
                    ("pre_generation_authorized",),
                )
            if any(pattern.search(payload.content) for pattern in _INSTRUCTION_PATTERNS):
                return GateDecision(
                    False,
                    "document_instruction_blocked",
                    outcome.ledger,
                    None,
                    ("document_content_safe",),
                )
            eligible.append(item)

        requirement = request.requirement
        keys = {item.payload.document_key for item in eligible if isinstance(item.payload, DocumentEvidencePayload)}
        types = {item.payload.knowledge_type for item in eligible if isinstance(item.payload, DocumentEvidencePayload)}
        searchable = _normalize(
            "\n".join(
                f"{item.payload.title}\n{item.payload.content}"
                for item in eligible
                if isinstance(item.payload, DocumentEvidencePayload)
            )
        )
        sufficient = (
            len(eligible) >= requirement.min_evidence
            and set(requirement.required_document_keys) <= keys
            and set(requirement.required_knowledge_types) <= types
            and all(_normalize(term) in searchable for term in requirement.required_terms)
        )
        if not sufficient:
            return GateDecision(
                False,
                "evidence_insufficient",
                outcome.ledger,
                None,
                ("structured_sufficiency",),
            )

        # 只把实际会传给 Composer 的前 max_claims 份 Evidence 推进，而不是把全部 selected
        # 一次性标成可见。这个细节是 M33 对“四阶段 Evidence”最重要的真实性保证。
        visible = tuple(eligible[: requirement.max_claims])
        visible_ids = tuple(item.ref.evidence_id for item in visible)
        context_identity = _hash(
            "generation-context",
            request.run_id,
            bundle.release_identity,
            requirement.identity,
            *(f"{item.ref.evidence_id}:{item.ref.content_identity}" for item in visible),
        )
        context = GenerationContext(
            run_id=request.run_id,
            context_identity=context_identity,
            requirement_identity=requirement.identity,
            release_identity=bundle.release_identity,
            evidence=visible,
        )
        try:
            visible_ledger = outcome.ledger.transition(
                evidence_ids=visible_ids,
                to_stage="generation_visible",
                generation_authorizations=auth_map,
            )
        except EvidenceContractError as exc:
            raise AnswerFlowContractError("gate_transition_invalid", "generation-visible 迁移失败") from exc
        return GateDecision(
            True,
            "answer_allowed",
            visible_ledger,
            context,
            (
                "selected_current",
                "pre_generation_authorized",
                "document_content_safe",
                "structured_sufficiency",
            ),
        )

    def _validate_claim_drafts(
        self,
        *,
        drafts: tuple[ClaimDraft, ...],
        context: GenerationContext,
        max_claims: int,
    ) -> None:
        """拒绝空答、越预算、未知 Evidence、错误 anchor、伪造 support 或重复 claim。

        这里刻意不要求 ``text`` 逐字出现在正文中：远程 Composer 可以生成更自然的
        paraphrase。安全锚点是 ``support_text``，它必须逐字属于同一个 Evidence；之后
        既有 citation validator 仍负责 Evidence 身份、授权、revision 和 slot 完整性。
        """

        if not drafts or len(drafts) > max_claims:
            raise AnswerFlowContractError("composer_output_invalid", "claim 数量为空或越预算")
        evidence = {item.ref.evidence_id: item for item in context.evidence}
        seen: set[tuple[str, str]] = set()
        for draft in drafts:
            item = evidence.get(draft.evidence_id)
            identity = (draft.text.strip(), draft.evidence_id)
            if (
                not draft.text.strip()
                or not draft.support_text.strip()
                or item is None
                or draft.anchor != item.ref.anchor
                or identity in seen
            ):
                raise AnswerFlowContractError("composer_output_invalid", "claim support/anchor/identity 非法")
            # ★ support 必须逐字来自绑定 Evidence；不能用另一份文档的正确原文冒充。
            payload = item.payload
            if not isinstance(payload, DocumentEvidencePayload) or draft.support_text not in payload.content:
                raise AnswerFlowContractError("composer_output_invalid", "claim support 不是绑定 Evidence 的逐字内容")
            seen.add(identity)

    def _build_citation_drafts(
        self,
        *,
        run_id: str,
        drafts: tuple[ClaimDraft, ...],
    ) -> tuple[tuple[CitationSlot, ...], tuple[CitationDraft, ...], tuple[str, ...]]:
        """由代码分配 claim/slot；private method 允许故障测试篡改但不是调用者 interface。"""

        slots: list[CitationSlot] = []
        citations: list[CitationDraft] = []
        claim_refs: list[str] = []
        for ordinal, draft in enumerate(drafts, start=1):
            claim_ref = _hash("claim", run_id, str(ordinal), draft.evidence_id, sha256(draft.text.encode()).hexdigest())
            slot = allocate_citation_slot(run_id=run_id, claim_ref=claim_ref, ordinal=1)
            slots.append(slot)
            citations.append(
                CitationDraft(
                    run_id=run_id,
                    slot_id=slot.slot_id,
                    claim_ref=claim_ref,
                    evidence_id=draft.evidence_id,
                    anchor=draft.anchor,
                )
            )
            claim_refs.append(claim_ref)
        return tuple(slots), tuple(citations), tuple(claim_refs)

    @staticmethod
    def _validate_complete_citation_set(
        *, slots: tuple[CitationSlot, ...], citations: tuple[ValidatedCitation, ...]
    ) -> None:
        """补足底层 validator 的调用方合同：每个预分配 slot 必须恰好返回一次。"""

        if tuple(item.slot_id for item in citations) != tuple(item.slot_id for item in slots):
            raise EvidenceContractError("citation_invalid", "validated citation 没有覆盖全部 slot")

    @staticmethod
    def _validated_output(
        *,
        drafts: tuple[ClaimDraft, ...],
        claim_refs: tuple[str, ...],
        validated: tuple[ValidatedCitation, ...],
        ledger: EvidenceLedger,
        current_entries: Mapping[tuple[str, str], CatalogEntry],
    ) -> tuple[tuple[ValidatedClaim, ...], tuple[UserCitation, ...]]:
        """只从 validator 输出构造 claims/citations，禁止读取未验证 draft 作为事实源。"""

        entry_map = current_entries
        citations_by_claim: dict[str, list[str]] = {}
        user_citations: list[UserCitation] = []
        for item in validated:
            evidence = ledger.evidence_by_id(item.evidence_ref.evidence_id)
            if not isinstance(evidence.payload, DocumentEvidencePayload):
                raise AnswerFlowContractError("citation_projection_invalid", "RAG citation 必须指向文档")
            entry = entry_map[(evidence.payload.document_key, evidence.payload.revision)]
            citations_by_claim.setdefault(item.claim_ref, []).append(item.slot_id)
            user_citations.append(
                UserCitation(
                    citation_id=item.slot_id,
                    claim_ref=item.claim_ref,
                    title=entry.title,
                    revision=entry.revision,
                    anchor=entry.anchor,
                    authority_ref=entry.authority_ref,
                )
            )
        claims = tuple(
            ValidatedClaim(
                claim_ref=claim_ref,
                text=draft.text,
                citation_ids=tuple(citations_by_claim[claim_ref]),
            )
            for draft, claim_ref in zip(drafts, claim_refs, strict=True)
        )
        return claims, tuple(user_citations)

    def _from_retrieval_failure(
        self,
        *,
        request: RAGAnswerRequest,
        outcome: RetrievalOutcome,
        started_at: float,
        counts: tuple[int, int, int, int],
        evidence_validity: dict[str, Any],
    ) -> RAGAnswerResult | None:
        """把 M32 取证事实投影到四轴，保持技术、安全和业务失败正交。"""

        del request  # 显式证明失败投影不需要重新解析 question 或 caller 内容。
        if outcome.reason_code == "evidence_retrieved":
            return None
        if outcome.reason_code == "no_candidate":
            values = ("completed", "insufficient_evidence", "passed", "evidence_no_candidate")
        elif outcome.reason_code == "stale_revision":
            values = ("completed", "insufficient_evidence", "passed", "document_revision_inactive")
        elif outcome.reason_code == "no_authorized_evidence":
            values = ("completed", "no_answer", "blocked", "document_acl_denied")
        elif outcome.reason_code == "active_release_unavailable":
            values = ("external_unavailable", "no_answer", "passed", "active_release_unavailable")
        else:
            values = ("external_unavailable", "no_answer", "passed", "retrieval_unavailable")
        execution, answer, safety, reason = values
        return self._failure_result(
            outcome=outcome,
            execution_status=execution,
            answer_status=answer,
            safety_status=safety,
            reason_code=reason,
            gate_decision=None,
            started_at=started_at,
            counts=counts,
            evidence_validity=evidence_validity,
        )

    def _from_gate_denial(
        self,
        *,
        outcome: RetrievalOutcome,
        gate: GateDecision,
        bundle: KnowledgeBundleView,
        started_at: float,
        counts: tuple[int, int, int, int],
        evidence_validity: dict[str, Any],
    ) -> RAGAnswerResult:
        """Gate deny 不调用 Composer/validator，并按 reason 唯一映射四轴。"""

        if gate.reason_code in {"evidence_insufficient", "document_revision_inactive"}:
            answer_status: AnswerStatus = "insufficient_evidence"
            safety_status: SafetyStatus = "passed"
        else:
            answer_status = "no_answer"
            safety_status = "blocked"
        reason: AnswerReason = gate.reason_code
        return self._failure_result(
            outcome=outcome,
            execution_status="completed",
            answer_status=answer_status,
            safety_status=safety_status,
            reason_code=reason,
            gate_decision=gate,
            started_at=started_at,
            counts=counts,
            bundle=bundle,
            evidence_validity=evidence_validity,
        )

    def _failure_result(
        self,
        *,
        outcome: RetrievalOutcome,
        execution_status: ExecutionStatus,
        answer_status: AnswerStatus,
        safety_status: SafetyStatus,
        reason_code: AnswerReason,
        gate_decision: GateDecision | None,
        started_at: float,
        counts: tuple[int, int, int, int],
        bundle: KnowledgeBundleView | None = None,
        evidence_validity: dict[str, Any] | None = None,
    ) -> RAGAnswerResult:
        """集中构造无答卷结果，防止某条错误分支意外保留 claim/citation。"""

        return RAGAnswerResult(
            route_status="rag",
            execution_status=execution_status,
            answer_status=answer_status,
            safety_status=safety_status,
            reason_code=reason_code,
            answer=None,
            claims=(),
            citations=(),
            ledger=gate_decision.ledger if gate_decision else outcome.ledger,
            gate_decision=gate_decision,
            retrieval_reason=outcome.reason_code,
            diagnostics=self._diagnostics(
                outcome=outcome,
                started_at=started_at,
                counts=counts,
                bundle=bundle,
                context=gate_decision.context if gate_decision else None,
            ),
            evidence_validity=evidence_validity or {},
        )

    def _diagnostics(
        self,
        *,
        outcome: RetrievalOutcome,
        started_at: float,
        counts: tuple[int, int, int, int],
        bundle: KnowledgeBundleView | None,
        context: GenerationContext | None,
    ) -> AnswerFlowDiagnostics:
        """所有成功/失败路径共享一份字段齐全的 runtime diagnostics。"""

        tool_calls, gate_calls, composer_calls, validator_calls = counts
        context_evidence = context.evidence if context else ()
        return AnswerFlowDiagnostics(
            runtime_identity=ANSWER_FLOW_RUNTIME_IDENTITY,
            composer_identity=self._composer.identity,
            release_identity=bundle.release_identity if bundle else outcome.diagnostics.release_identity,
            corpus_identity=bundle.corpus_identity if bundle else outcome.diagnostics.corpus_identity,
            retrieval_adapter_identity=outcome.diagnostics.adapter_identity,
            retrieval_recipe_identity=outcome.diagnostics.recipe_identity,
            authorization_policy_identity=(
                bundle.authorization_policy_identity if bundle else DOCUMENT_AUTHORIZATION_POLICY_IDENTITY
            ),
            outbound_policy_identity=(
                bundle.outbound_policy_identity if bundle else OUTBOUND_POLICY_IDENTITY
            ),
            knowledge_tool_calls=tool_calls,
            gate_calls=gate_calls,
            composer_calls=composer_calls,
            validator_calls=validator_calls,
            context_count=len(context_evidence),
            context_characters=sum(
                len(item.payload.content)
                for item in context_evidence
                if isinstance(item.payload, DocumentEvidencePayload)
            ),
            elapsed_ms=round((perf_counter() - started_at) * 1000, 3),
        )
