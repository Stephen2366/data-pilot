"""M41 专用 business Knowledge 真实 Composer 与窄出站策略。

该策略不进入普通 API。CLI 必须显式构造本 wrapper；wrapper 在网络调用前重新对照 active
release，确保 Composer 看到的每份 Evidence 都来自当前 release、已经进入 generation context，
且数据类别属于用户确认的窄白名单。
"""

from __future__ import annotations

from typing import Any

from engine.governance import OutboundPolicy, OutboundRule
from engine.rag.answer_flow import ClaimDraft, ComposerUnavailableError, EvidenceComposer, GenerationContext
from engine.rag.enterprise_generation import make_qwen_evidence_composer
from engine.rag.evidence import DocumentEvidencePayload
from engine.rag.release import load_active_release
from eval.rag_e2e_contracts import RAGEvalContractError


RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY = "phase4-rag-eval-business-generation-outbound-v1"
RAG_EVAL_BUSINESS_DATA_CLASS = "business_knowledge_eval_prompt"
RAG_EVAL_ALLOWED_SOURCE_CLASSES = frozenset({"role_restricted_policy_text", "metric_definition"})
RAG_EVAL_BUSINESS_OUTBOUND_POLICY = OutboundPolicy(
    identity=RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY,
    rules=(
        OutboundRule(
            "qwen_chat", "knowledge_answer_generation", RAG_EVAL_BUSINESS_DATA_CLASS,
            frozenset({"prompt", "system_prompt", "model"}),
        ),
    ),
)


class BusinessEvalEvidenceComposer:
    """先做 release/data-class 复核，再把 generation context 交给真实 Composer。"""

    def __init__(self, delegate: EvidenceComposer) -> None:
        self._delegate = delegate
        self.identity = f"rag-business-eval-guard-v1:{delegate.identity}"
        self.attempts: list[dict[str, Any]] = []

    def usage_projection(self) -> dict[str, int]:
        """沿用真实 provider 的计费数字；guard 自身不伪造 token。"""

        projection = getattr(self._delegate, "usage_projection", None)
        return dict(projection()) if callable(projection) else {}

    def compose(
        self, *, context: GenerationContext, question: str,
        confirmed_conditions: tuple[str, ...], max_claims: int,
    ) -> tuple[ClaimDraft, ...]:
        """★ 在真实网络调用前重验 active release、Evidence 用途和数据类别。"""

        # 步骤 1：把 generation context 重新绑定到当前 active release =====================
        _pointer, bundle = load_active_release()
        entries = {
            (entry.document_key, entry.revision, entry.content_identity, entry.anchor): entry
            for entry in bundle.entries
        }
        source_classes: set[str] = set()
        for evidence in context.evidence:
            payload = evidence.payload
            if not isinstance(payload, DocumentEvidencePayload):
                raise RAGEvalContractError("rag_eval_outbound_evidence_invalid", "只允许 Document Evidence")
            key = (payload.document_key, payload.revision, evidence.ref.content_identity, payload.anchor)
            entry = entries.get(key)
            if (
                payload.release_identity != bundle.release_identity
                or entry is None
                or entry.content != payload.content
                or "answer_evidence" not in evidence.allowed_uses
            ):
                raise RAGEvalContractError("rag_eval_outbound_evidence_invalid", payload.document_key)
            source_classes.add(entry.data_class)
        # 步骤 2：执行用户确认的 eval-only 数据类别白名单 -------------------------------
        disallowed = source_classes - RAG_EVAL_ALLOWED_SOURCE_CLASSES
        if not source_classes or disallowed:
            self.attempts.append({
                "status": "failed", "error_subtype": "eval_outbound_data_class_denied",
                "eval_outbound_policy_identity": RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY,
                "authorized_source_data_classes": sorted(source_classes),
                "authorized_document_count": 0,
            })
            raise ComposerUnavailableError("M41 eval-only outbound preflight denied")
        delegate_attempts = getattr(self._delegate, "attempts", [])
        attempts_before = len(delegate_attempts)
        # 步骤 3：调用 delegate，并只记录无正文的出站审计摘要 ---------------------------
        try:
            return self._delegate.compose(
                context=context, question=question, confirmed_conditions=confirmed_conditions,
                max_claims=max_claims,
            )
        finally:
            # 只追加类别和计数，不记录 document key、正文或 prompt。
            raw = delegate_attempts[-1] if len(delegate_attempts) > attempts_before else {"status": "unknown"}
            self.attempts.append({
                **dict(raw),
                "eval_outbound_policy_identity": RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY,
                "authorized_source_data_classes": sorted(source_classes),
                "authorized_document_count": len(context.evidence),
            })


def make_business_qwen_eval_composer(
    *, api_key: str, base_url: str, model: str, timeout: float,
) -> BusinessEvalEvidenceComposer:
    """M41 CLI 的唯一真实 Composer factory；默认业务路径不会调用。"""

    delegate = make_qwen_evidence_composer(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        outbound_policy=RAG_EVAL_BUSINESS_OUTBOUND_POLICY,
        outbound_data_class=RAG_EVAL_BUSINESS_DATA_CLASS,
        identity="rag-qwen-business-eval-support-nonthinking-v1",
    )
    return BusinessEvalEvidenceComposer(delegate)
