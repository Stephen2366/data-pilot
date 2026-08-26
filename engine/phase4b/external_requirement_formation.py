"""M46-D0：从开放 external 问题形成可审计的 typed Evidence requirement。

这个 deep module 位于 initial retrieval 与 RAG action executor 之间。调用方只提交问题和
本轮已经授权的 Document Evidence；implementation 内部负责 deterministic procedure、受控
structured supplier、question source-span 校验、focused query 组装、coverage 重算和 typed stop。

★ 模型只提出 atomic obligation，不拥有最终 query、coverage 或 action 决策。这样既保留语言
理解能力，又不把 M45 的 action executor 或 Evidence Gate 偷偷升级为自由 planner。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Literal, Protocol

from engine.nl2sql.generator import LLMGenerationError
from engine.phase4b.identity import canonical_hash
from engine.phase4b.rag_diagnostics import RequirementSlot
from engine.phase4b.rag_recovery_requirement_proposal import B4ProposalTransport
from engine.rag.evidence import DocumentEvidencePayload, Evidence

FormationReason = Literal["requested_fact", "requested_procedure"]
QualifierCategory = Literal["none", "current_authority"]
RecoveryAction = Literal["query_rewrite_candidate", "context_expansion_candidate"]
ValueShape = Literal["none", "numeric", "duration", "schedule", "ordered_steps"]

FORMATION_IDENTITY = "phase4b-b4-external-requirement-formation-v3"
PROCEDURE_SUPPLIER_IDENTITY = "phase4b-b4-procedure-supplier-v1"
QUESTION_SUPPLIER_IDENTITY = "phase4b-b4-question-obligation-supplier-v1"
OBLIGATION_SCHEMA_VERSION = "phase4b-b4-question-obligation-proposal-v1"
OBLIGATION_PROMPT_IDENTITY = "phase4b-b4-question-obligation-prompt-v2"
OBLIGATION_PURPOSE = "rag_recovery_requirement_proposal"

_WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]+")
_SPAN_STOPWORDS = frozenset({
    "and", "are", "does", "for", "from", "how", "is", "of", "the", "to", "use", "uses", "what", "which",
})
_CURRENT_CUES = frozenset({
    "active", "approved", "authoritative", "current", "currently", "effective", "latest", "now",
})
_PROCEDURE_CUES = frozenset({"checklist", "procedure", "rollback", "steps", "workflow"})
_CURRENT_QUALIFIERS = ("current", "updated", "approved", "effective", "authoritative", "active", "latest")


class RequirementFormationError(ValueError):
    """supplier/schema/source-span/coverage 的 closed-world 失败。"""

    def __init__(
        self,
        reason_code: str,
        *,
        usage: "FormationUsage | None" = None,
        prompt: str = "",
        raw_response: str = "",
    ) -> None:
        self.reason_code = reason_code
        self.usage = usage
        self.prompt = prompt
        self.raw_response = raw_response
        super().__init__(reason_code)


@dataclass(frozen=True)
class FormationUsage:
    """D0 自己拥有的 provider 计账；失败也不能被投影成零调用。"""

    model: str = "none"
    calls: int = 0
    total_tokens: int = 0
    token_usage_observed: bool = True

    def safe_projection(self) -> dict[str, Any]:
        """公开计账数字与模型名，不保存 prompt 或 provider 响应。"""

        return {
            "model": self.model,
            "calls": self.calls,
            "total_tokens": self.total_tokens,
            "token_usage_observed": self.token_usage_observed,
        }


@dataclass(frozen=True)
class ExternalRequirementFormationInput:
    """D0 的小 interface：不暴露 RAGAnswerRequest、RetrievalOutcome 或 qst/gold。"""

    question: str
    current_evidence: tuple[Evidence, ...]
    max_requirements: int = 2


@dataclass(frozen=True)
class AtomicObligation:
    """模型可提议的最小语义；所有自由文本都必须是 question source span。"""

    identity: str
    reason_category: FormationReason
    question_anchor: str
    requested_aspect: str
    entity_constraints: tuple[str, ...]
    qualifier_category: QualifierCategory
    value_shape: ValueShape


@dataclass(frozen=True)
class AtomicObligationBatch:
    """Supplier 的原子义务批次及其可核对 usage/fingerprint。"""

    obligations: tuple[AtomicObligation, ...]
    usage: FormationUsage
    prompt_fingerprint: str
    response_fingerprint: str


@dataclass(frozen=True)
class FormedRequirement:
    """additive wrapper：保留 M45 RequirementSlot 签名，同时补齐 C2-ERF 来源事实。"""

    slot: RequirementSlot
    supplier_identity: str
    formation_reason_category: FormationReason
    allowed_recovery_actions: tuple[RecoveryAction, ...]
    coverage_semantics: str = "single_authorized_document_all_groups_v1"

    def safe_projection(self) -> dict[str, Any]:
        """仅公开控制面事实，不把形成阶段的自由文本写入 artifact。"""

        return {
            # 模型产生的 obligation identity 可能携带题意，不能复用 M45 diagnostic 的旧
            # safe projection。D0 只公开不可逆签名/指纹与计数。
            "slot_signature": self.slot.signature,
            "focused_query_fingerprint": canonical_hash(self.slot.focused_query),
            "support_group_count": len(self.slot.support_marker_groups),
            "supplier_identity": self.supplier_identity,
            "formation_reason_category": self.formation_reason_category,
            "allowed_recovery_actions": list(self.allowed_recovery_actions),
            "coverage_semantics": self.coverage_semantics,
        }


@dataclass(frozen=True)
class RequirementFormationResult:
    """formation 的唯一返回类型；无 requirement 也是显式 typed stop。"""

    requirements: tuple[FormedRequirement, ...] = ()
    continuation_policy: Literal["disabled", "procedure_boundary_v1"] = "disabled"
    decision: str = "typed_stop"
    reason_code: str = "not_applicable"
    usage: FormationUsage = FormationUsage()
    prompt_fingerprint: str = "not_observed"
    response_fingerprint: str = "not_observed"
    failure_reason: str | None = None

    def safe_projection(self) -> dict[str, Any]:
        """输出 formation 决策、usage 与不可逆指纹的安全投影。"""

        return {
            "formation_identity": FORMATION_IDENTITY,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "requirements": [item.safe_projection() for item in self.requirements],
            "usage": self.usage.safe_projection(),
            "prompt_fingerprint": self.prompt_fingerprint,
            "response_fingerprint": self.response_fingerprint,
        }


class AtomicObligationSupplier(Protocol):
    """true external Qwen 的 internal seam；测试用 fake adapter，不泄漏到 D0 interface。"""

    identity: str

    def propose(self, formation_input: ExternalRequirementFormationInput) -> AtomicObligationBatch:
        """根据公开问题与已授权 Evidence 提议有限个原子义务。"""

        ...


def _document_text(evidence: tuple[Evidence, ...]) -> tuple[str, ...]:
    """只返回已授权 Document Evidence 正文；非文档 Evidence 不参与 coverage。"""

    return tuple(
        item.payload.content.casefold()
        for item in evidence
        if isinstance(item.payload, DocumentEvidencePayload) and item.payload.content.strip()
    )


def _is_source_span(*, question: str, value: str) -> bool:
    """允许用户自己给出的 EXP-002/日期/阈值，拒绝模型新造的答案值。"""

    normalized = " ".join(value.casefold().split())
    return bool(normalized) and normalized in " ".join(question.casefold().split())


def _question_tokens(value: str) -> tuple[str, ...]:
    """抽取去重后的问题 token，供 source-span 与最低信息量校验。"""

    return tuple(dict.fromkeys(_WORD_PATTERN.findall(value.casefold())))


def _build_prompt(formation_input: ExternalRequirementFormationInput) -> str:
    """Qwen 只看公开问题和最多三条授权 Evidence；不发送 title/key/coordinates。"""

    question = formation_input.question.strip()
    evidence_texts = _document_text(formation_input.current_evidence)
    if not question or len(question) > 1000:
        raise RequirementFormationError("formation_question_invalid")
    if not evidence_texts:
        raise RequirementFormationError("formation_authorized_evidence_missing")
    evidence_block = "\n\n".join(
        f"[E{index}]\n{text[:4000]}" for index, text in enumerate(evidence_texts[:3], start=1)
    )
    return f"""Question:\n{question}\n\nCurrent authorized evidence:\n{evidence_block}\n\n
Return strict JSON with exactly this shape:
{{"obligations":[{{"reason_category":"requested_fact|requested_procedure","question_anchor":"exact meaningful span copied from Question","requested_aspect":"exact meaningful span copied from Question","entity_constraints":["zero to three exact meaningful spans copied from Question"],"qualifier_category":"none|current_authority","value_shape":"none|numeric|duration|schedule|ordered_steps"}}]}}

Return 1-{formation_input.max_requirements} independently checkable atomic obligations needed to answer the Question. Every question_anchor, requested_aspect, and entity constraint must be one exact contiguous span copied from the Question; preserve its wording and never paraphrase. Never copy document IDs/titles and never invent answer values. Use current_authority only when the Question explicitly says active, approved, authoritative, current, currently, effective, latest, or now. Ordinary present-tense wording such as does/use/uses is not a current-authority request. Do not write a focused query, support markers, coverage verdict, citations, answer, prose, or extra keys.
"""


class B4QuestionObligationSupplier:
    """一次 Qwen proposal；解析后仍不形成 query，全部控制交给 D0 validator。"""

    identity = QUESTION_SUPPLIER_IDENTITY

    def __init__(self, transport: B4ProposalTransport) -> None:
        self._transport = transport

    def propose(self, formation_input: ExternalRequirementFormationInput) -> AtomicObligationBatch:
        """执行一次 bounded Qwen 调用并解析为尚未获授权的义务提案。"""

        prompt = _build_prompt(formation_input)
        before_calls = self._transport.request_count
        before_tokens = self._transport.total_tokens
        try:
            raw = self._transport.complete(
                prompt=prompt,
                system_prompt=(
                    "You are a bounded retrieval requirement supplier. Output strict JSON only. "
                    "Never answer, judge coverage, select a tool, or invent answer values."
                ),
                node_purpose=OBLIGATION_PURPOSE,
            )
        except LLMGenerationError as exc:
            usage = FormationUsage(
                model=self._transport.model,
                calls=self._transport.request_count - before_calls,
                total_tokens=self._transport.total_tokens - before_tokens,
                token_usage_observed=False,
            )
            raise RequirementFormationError(
                f"formation_supplier_{exc.error_subtype or 'transport_failed'}", usage=usage, prompt=prompt,
            ) from exc
        usage = FormationUsage(
            model=self._transport.model,
            calls=self._transport.request_count - before_calls,
            total_tokens=self._transport.total_tokens - before_tokens,
            token_usage_observed=True,
        )
        if usage.calls != 1 or usage.total_tokens < 0:
            raise RequirementFormationError("formation_supplier_usage_invalid", usage=usage)
        try:
            obligations = _validate_obligation_payload(
                raw=raw,
                question=formation_input.question,
                max_requirements=formation_input.max_requirements,
            )
        except RequirementFormationError as exc:
            exc.usage = usage
            exc.prompt = prompt
            exc.raw_response = raw
            raise
        return AtomicObligationBatch(
            obligations=obligations,
            usage=usage,
            prompt_fingerprint=canonical_hash(prompt),
            response_fingerprint=canonical_hash(raw),
        )


def _validate_obligation_payload(
    *, raw: str, question: str, max_requirements: int
) -> tuple[AtomicObligation, ...]:
    """校验 closed schema 与 question source span；不接触 Evidence/gold。"""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RequirementFormationError("formation_supplier_json_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"obligations"}:
        raise RequirementFormationError("formation_supplier_schema_invalid")
    rows = payload["obligations"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= max_requirements:
        raise RequirementFormationError("formation_supplier_count_invalid")
    expected = {
        "reason_category", "question_anchor", "requested_aspect",
        "entity_constraints", "qualifier_category", "value_shape",
    }
    obligations: list[AtomicObligation] = []
    question_token_set = set(_question_tokens(question))
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected:
            raise RequirementFormationError("formation_obligation_schema_invalid")
        reason = row["reason_category"]
        anchor = row["question_anchor"]
        aspect = row["requested_aspect"]
        constraints = row["entity_constraints"]
        qualifier = row["qualifier_category"]
        value_shape = row["value_shape"]
        if reason not in {"requested_fact", "requested_procedure"}:
            raise RequirementFormationError("formation_reason_category_invalid")
        if (
            not isinstance(anchor, str)
            or not 3 <= len(anchor.strip()) <= 160
            or not _is_source_span(question=question, value=anchor)
            or not _meaningful_span(anchor)
        ):
            raise RequirementFormationError("formation_question_anchor_not_source_spanned")
        if (
            not isinstance(aspect, str)
            or not 2 <= len(aspect.strip()) <= 120
            or not _is_source_span(question=question, value=aspect)
            or not _meaningful_span(aspect)
        ):
            raise RequirementFormationError("formation_requested_aspect_not_source_spanned")
        if not isinstance(constraints, list) or len(constraints) > 3:
            raise RequirementFormationError("formation_entity_constraints_invalid")
        normalized_constraints: list[str] = []
        for constraint in constraints:
            if (
                not isinstance(constraint, str)
                or not 2 <= len(constraint.strip()) <= 80
                or not _is_source_span(question=question, value=constraint)
                or not _meaningful_span(constraint)
            ):
                raise RequirementFormationError("formation_entity_constraint_not_source_spanned")
            normalized_constraints.append(constraint.strip())
        if qualifier not in {"none", "current_authority"}:
            raise RequirementFormationError("formation_qualifier_category_invalid")
        if qualifier == "current_authority" and not (question_token_set & _CURRENT_CUES):
            # ★ qualifier 是模型给出的闭集标签，不是题面事实。题面没有明确 freshness cue 时，
            # 服务端可以安全地把“过度分类”降为 none；这不会发明新约束，也不会放宽后续
            # source-span、value-shape、Evidence grounding 或 action validator。
            qualifier = "none"
        if value_shape not in {"none", "numeric", "duration", "schedule", "ordered_steps"}:
            raise RequirementFormationError("formation_value_shape_invalid")
        expected_shape = _expected_value_shape(aspect=aspect, reason=reason)
        if value_shape != expected_shape:
            # value shape 和 qualifier 一样只是模型的闭集标签；真正的 Evidence 形状要求由
            # 服务端从题面 aspect/reason 确定。规范化不会放宽 Gate，rate→numeric 反而阻止
            # 模型把数值问题降级成无需数值证据。
            value_shape = expected_shape
        identity_payload = {
            'reason': reason,
            'aspect': aspect.casefold(),
            'constraints': [item.casefold() for item in normalized_constraints],
            'qualifier': qualifier,
            'value_shape': value_shape,
        }
        identity = (
            f"question_obligation_{len(obligations) + 1}_"
            f"{canonical_hash(identity_payload)[:12]}"
        )
        obligations.append(AtomicObligation(
            identity=identity,
            reason_category=reason,
            question_anchor=anchor.strip(),
            requested_aspect=aspect.strip(),
            entity_constraints=tuple(dict.fromkeys(normalized_constraints)),
            qualifier_category=qualifier,
            value_shape=value_shape,
        ))
    return tuple(obligations)


def _meaningful_span(value: str) -> bool:
    """阻止 ``the/what`` 等弱锚点通过 exact-source-span 形式校验。"""

    return any(
        len(token) >= 3 and token not in _SPAN_STOPWORDS
        for token in _question_tokens(value)
    )


def _expected_value_shape(*, aspect: str, reason: FormationReason) -> ValueShape:
    """模型可提议 shape，但不能用 ``none`` 降低明显数值/流程要求的 coverage。"""

    tokens = set(_question_tokens(aspect))
    if reason == "requested_procedure" or tokens & {"checklist", "procedure", "steps", "workflow"}:
        return "ordered_steps"
    if tokens & {"duration", "latency", "timeframe", "timeout"}:
        return "duration"
    if tokens & {"calendar", "schedule", "timetable"}:
        return "schedule"
    if tokens & {"amount", "cost", "count", "percentage", "price", "rate", "ratio", "total"}:
        return "numeric"
    return "none"


def _procedure_requirements(question: str) -> tuple[FormedRequirement, ...]:
    """保留 M45 procedure trigger 的窄语义，并在 wrapper 中固定 expansion-only。"""

    tokens = set(_question_tokens(question))
    if not (tokens & _PROCEDURE_CUES):
        return ()
    slots = [RequirementSlot(
        "procedure_core",
        "operational procedure rollback workflow steps",
        (("procedure", "steps", "workflow"),),
        marker_match_mode="token_overlap",
    )]
    if {"hosted", "dedicated"} <= tokens:
        slots.append(RequirementSlot(
            "environment_variants",
            "procedure hosted dedicated environment variants",
            (("hosted",), ("dedicated",)),
            marker_match_mode="token_overlap",
        ))
    return tuple(FormedRequirement(
        slot=slot,
        supplier_identity=PROCEDURE_SUPPLIER_IDENTITY,
        formation_reason_category="requested_procedure",
        allowed_recovery_actions=("context_expansion_candidate",),
    ) for slot in slots)


def _assemble_requirement(
    obligation: AtomicObligation,
    *,
    question: str,
    current_evidence: tuple[Evidence, ...],
) -> FormedRequirement:
    """服务端拥有 focused query/marker；模型的 source spans 只是受控输入。"""

    groups: list[tuple[str, ...]] = [
        (constraint.casefold(),) for constraint in obligation.entity_constraints
    ]
    groups.append((obligation.requested_aspect.casefold(),))
    if obligation.qualifier_category == "current_authority":
        groups.append(_CURRENT_QUALIFIERS)
    # RequirementSlot 最多只需 5 组；超出说明 supplier 把 interface 当自由 DSL 使用。
    if len(groups) > 5:
        raise RequirementFormationError("formation_support_group_budget_exceeded")
    query_parts = [*obligation.entity_constraints, obligation.requested_aspect]
    if obligation.qualifier_category == "current_authority":
        query_parts.append("current authoritative effective")
    slot = RequirementSlot(
        identity=obligation.identity,
        focused_query=" ".join(query_parts),
        support_marker_groups=tuple(groups),
        value_shape=obligation.value_shape,
        marker_match_mode="token_overlap",
    )
    # ★ Grounding 由服务端基于完整问题计算，不能让模型通过选择某个窄 anchor 决定准入。
    # 这里只做个人项目所需的轻量共同词门禁；不额外调用 embedding/LLM Judge。
    texts = _document_text(current_evidence)
    question_tokens = {
        token for token in _question_tokens(question)
        if len(token) >= 3 and token not in _SPAN_STOPWORDS
    }
    if not texts or not any(
        question_tokens & set(_question_tokens(text)) for text in texts
    ):
        raise RequirementFormationError("formation_no_grounded_evidence_anchor")
    return FormedRequirement(
        slot=slot,
        supplier_identity=QUESTION_SUPPLIER_IDENTITY,
        formation_reason_category=obligation.reason_category,
        allowed_recovery_actions=("query_rewrite_candidate", "context_expansion_candidate"),
    )


class ExternalRequirementFormer:
    """C2-ERF deep module：一个 ``form`` interface 隐藏全部 supplier/validator 复杂度。"""

    identity = FORMATION_IDENTITY

    def __init__(self, *, structured_supplier: AtomicObligationSupplier | None = None) -> None:
        self._structured_supplier = structured_supplier

    def form(self, formation_input: ExternalRequirementFormationInput) -> RequirementFormationResult:
        """procedure → structured obligations → deterministic coverage → typed stop。"""

        if formation_input.max_requirements != 2:
            return RequirementFormationResult(
                decision="typed_stop",
                reason_code="formation_requirement_budget_invalid",
                failure_reason="formation_requirement_budget_invalid",
            )
        procedure = _procedure_requirements(formation_input.question)
        if procedure:
            return RequirementFormationResult(
                requirements=procedure,
                continuation_policy="procedure_boundary_v1",
                decision="deterministic_procedure",
                reason_code="eligible",
            )
        if self._structured_supplier is None:
            return RequirementFormationResult(
                decision="typed_stop",
                reason_code="structured_supplier_unavailable",
                failure_reason="structured_supplier_unavailable",
            )
        batch: AtomicObligationBatch | None = None
        try:
            batch = self._structured_supplier.propose(formation_input)
            formed = tuple(
                _assemble_requirement(
                    item,
                    question=formation_input.question,
                    current_evidence=formation_input.current_evidence,
                )
                for item in batch.obligations
            )
        except RequirementFormationError as exc:
            # ★ supplier 已返回后，source-span 之外的 Evidence/coverage validator 仍可能失败。
            # 这时 provider call 和 token 已真实发生，不能退回默认 0；否则 Probe 会把一次
            # 出站调用错误记成“未调用”，也会丢失 prompt/response 的不可逆审计指纹。
            usage = batch.usage if batch is not None else (
                exc.usage or FormationUsage(token_usage_observed=False)
            )
            prompt_fingerprint = batch.prompt_fingerprint if batch is not None else (
                canonical_hash(exc.prompt) if exc.prompt else "not_observed"
            )
            response_fingerprint = batch.response_fingerprint if batch is not None else (
                canonical_hash(exc.raw_response) if exc.raw_response else "not_observed"
            )
            return RequirementFormationResult(
                decision="structured_supplier_failed",
                reason_code=exc.reason_code,
                usage=usage,
                prompt_fingerprint=prompt_fingerprint,
                response_fingerprint=response_fingerprint,
                failure_reason=exc.reason_code,
            )
        unsupported = tuple(item for item in formed if not item.slot.supported_by(formation_input.current_evidence))
        if not unsupported:
            return RequirementFormationResult(
                decision="typed_stop",
                reason_code="formation_no_unsupported_requirement",
                usage=batch.usage,
                prompt_fingerprint=batch.prompt_fingerprint,
                response_fingerprint=batch.response_fingerprint,
                failure_reason="formation_no_unsupported_requirement",
            )
        return RequirementFormationResult(
            requirements=unsupported,
            decision="structured_question_obligations",
            reason_code="eligible",
            usage=batch.usage,
            prompt_fingerprint=batch.prompt_fingerprint,
            response_fingerprint=batch.response_fingerprint,
        )
