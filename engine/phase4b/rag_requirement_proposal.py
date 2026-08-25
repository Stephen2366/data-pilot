"""M45-E：Evidence-aware 的结构化 requirement/rewrite proposal。

★ 模型在这里不是 Controller，也不直接判定 Evidence 是否足够。它只把“问题 + 当前已授权
Evidence”整理成 bounded requirement 候选；严格 schema validator、本地 marker/value-shape
coverage、ACL 和 recovery budget 仍是最终裁判。这样能利用模型理解开放措辞的能力，又不会把
自由文本决定直接接到 Tool 上。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Protocol

from engine.governance import OutboundPolicy, OutboundRule
from engine.nl2sql.generator import LLMGenerationError, QwenChatClient
from engine.phase4b.identity import canonical_hash
from engine.phase4b.rag_diagnostics import RequirementSlot, RequirementValueShape
from engine.rag.evidence import DocumentEvidencePayload, Evidence

PROPOSAL_SCHEMA_VERSION = "phase4b-m45-rag-requirement-proposal-v1"
PROPOSAL_PROMPT_IDENTITY = "m45-e-evidence-aware-requirement-proposal-v1"
PROPOSAL_OUTBOUND_IDENTITY = "phase4b-m45-rag-requirement-proposal-outbound-v1"
PROPOSAL_DATA_CLASS = "public_benchmark_question_with_authorized_evidence"
PROPOSAL_PURPOSE = "rag_requirement_proposal"
PROPOSAL_OUTBOUND_POLICY = OutboundPolicy(
    identity=PROPOSAL_OUTBOUND_IDENTITY,
    rules=(
        OutboundRule(
            "qwen_chat",
            PROPOSAL_PURPOSE,
            PROPOSAL_DATA_CLASS,
            frozenset({"prompt", "system_prompt", "model"}),
        ),
    ),
)

_VALUE_SHAPES: frozenset[str] = frozenset(
    {"none", "numeric", "duration", "schedule", "ordered_steps"}
)
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
_ANSWER_VALUE_PATTERN = re.compile(
    r"(?:[$€£]\s*\d|\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d+(?:\.\d+)?\s*%(?!\w))",
    re.IGNORECASE,
)
_FORBIDDEN_TEXT = ("gold", "reference answer", "reserve", "document_key", "unit_identity")
_QUESTION_STOPWORDS = {
    "what", "which", "when", "where", "who", "why", "how", "is", "are", "the", "a", "an",
    "and", "or", "of", "for", "to", "in", "on", "with", "does", "do", "get", "so",
}


class RequirementProposalError(ValueError):
    """proposal 在 transport/schema/安全边界上的稳定失败。"""

    def __init__(
        self, reason_code: str, message: str = "", *, prompt: str = "", raw_response: str = "",
        usage: "ProposalUsage | None" = None,
    ) -> None:
        self.reason_code = reason_code
        self.prompt = prompt
        self.raw_response = raw_response
        self.usage = usage
        super().__init__(f"{reason_code}: {message}" if message else reason_code)


class RequirementProposalTransport(Protocol):
    """测试可注入 fake；真实 adapter 复用既有 Qwen chat transport。"""

    model: str
    request_count: int
    total_tokens: int

    def complete(
        self, *, prompt: str, system_prompt: str | None = None, node_purpose: str
    ) -> str: ...


@dataclass(frozen=True)
class ProposalUsage:
    """只记录 calls/tokens，不保存 prompt 或模型原文。"""

    model: str
    calls: int
    total_tokens: int
    token_usage_observed: bool

    def safe_projection(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "calls": self.calls,
            "total_tokens": self.total_tokens,
            "token_usage_observed": self.token_usage_observed,
        }


@dataclass(frozen=True)
class RequirementProposal:
    """validator 接受后的 proposal；正文只在内存和项目外 private artifact 流转。"""

    slots: tuple[RequirementSlot, ...]
    prompt_fingerprint: str
    response_fingerprint: str
    usage: ProposalUsage
    prompt: str = ""
    raw_response: str = ""

    def safe_projection(self) -> dict[str, Any]:
        return {
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "prompt_identity": PROPOSAL_PROMPT_IDENTITY,
            "prompt_fingerprint": self.prompt_fingerprint,
            "response_fingerprint": self.response_fingerprint,
            "outbound_policy_identity": PROPOSAL_OUTBOUND_IDENTITY,
            "slot_projections": [slot.safe_projection() for slot in self.slots],
            "usage": self.usage.safe_projection(),
        }

    def private_projection(self) -> dict[str, Any]:
        """只允许写入项目外 diagnostic store；仓库 artifact 不得调用此投影。"""

        return {
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "prompt_identity": PROPOSAL_PROMPT_IDENTITY,
            "prompt": self.prompt,
            "raw_response": self.raw_response,
            "slots": [
                {
                    "identity": slot.identity,
                    "focused_query": slot.focused_query,
                    "support_marker_groups": [list(group) for group in slot.support_marker_groups],
                    "value_shape": slot.value_shape,
                    "marker_match_mode": slot.marker_match_mode,
                    "signature": slot.signature,
                }
                for slot in self.slots
            ],
            "usage": self.usage.safe_projection(),
        }


def make_qwen_requirement_proposal_client(
    *, api_key: str, base_url: str, model: str = "qwen3.7-plus", timeout: float = 120.0,
) -> QwenChatClient:
    """创建 M45 diagnostic-only client；不会修改全局/default outbound policy。"""

    return QwenChatClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        max_retries=0,
        outbound_policy=PROPOSAL_OUTBOUND_POLICY,
        outbound_data_class=PROPOSAL_DATA_CLASS,
        enable_thinking=False,
        max_tokens=1600,
    )


def _question_tokens(question: str) -> set[str]:
    """提取可用于 question/proposal 锚定的英文内容词，忽略常见虚词。"""

    return {
        token for token in re.findall(r"[a-z][a-z0-9_-]{2,}", question.casefold())
        if token not in _QUESTION_STOPWORDS
    }


def _build_prompt(*, question: str, evidence: tuple[Evidence, ...]) -> tuple[str, tuple[str, ...]]:
    """只投影 E1..E3 + 截断正文；title/key/coordinates 不进入 outbound。"""

    if not question.strip() or len(question) > 1000:
        raise RequirementProposalError("proposal_question_invalid")
    snippets: list[str] = []
    for item in evidence[:3]:
        if not isinstance(item.payload, DocumentEvidencePayload):
            raise RequirementProposalError("proposal_evidence_type_invalid")
        content = item.payload.content.strip()
        if not content:
            raise RequirementProposalError("proposal_evidence_empty")
        snippets.append(content[:4000])
    if not snippets:
        raise RequirementProposalError("proposal_evidence_missing")
    evidence_block = "\n\n".join(
        f"[E{index}]\n{content}" for index, content in enumerate(snippets, start=1)
    )
    prompt = f"""Question:\n{question.strip()}\n\nCurrent authorized evidence:\n{evidence_block}\n\n"
Return one JSON object with exactly this shape:
{{"requirements":[{{"requirement_id":"snake_case", "focused_query":"category-only retrieval query without answer values", "support_marker_groups":[["term or phrase"]], "value_shape":"none|numeric|duration|schedule|ordered_steps"}}]}}

List 1-5 independently checkable aspects required for a complete, operational answer. Each requirement must contain 1-5 support_marker_groups, and each group must contain 1-4 short alternative markers. Compare the question with the current evidence and make incomplete or missing aspects discriminative enough to retrieve adjacent context. Do not copy exact numeric/date/currency answer values. Do not mention evidence IDs, document titles, gold answers, or hidden data. Do not output a coverage verdict, citations, prose, or extra keys.
"""
    return prompt, tuple(snippets)


def validate_requirement_proposal(
    *, raw: str, question: str, current_evidence: tuple[Evidence, ...], prompt_fingerprint: str,
    usage: ProposalUsage,
) -> RequirementProposal:
    """严格解析模型 JSON，并只保留由本地 coverage 证明仍 unsupported 的 slots。"""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RequirementProposalError("proposal_json_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"requirements"}:
        raise RequirementProposalError("proposal_top_level_schema_invalid")
    rows = payload["requirements"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5:
        raise RequirementProposalError("proposal_requirement_count_invalid")

    question_tokens = _question_tokens(question)
    identities: set[str] = set()
    slots: list[RequirementSlot] = []
    for row in rows:
        required_keys = {"requirement_id", "focused_query", "support_marker_groups", "value_shape"}
        if not isinstance(row, dict) or set(row) != required_keys:
            raise RequirementProposalError("proposal_requirement_schema_invalid")
        identity = row["requirement_id"]
        focused_query = row["focused_query"]
        groups = row["support_marker_groups"]
        value_shape = row["value_shape"]
        if not isinstance(identity, str) or not _ID_PATTERN.fullmatch(identity) or identity in identities:
            raise RequirementProposalError("proposal_requirement_identity_invalid")
        if not isinstance(focused_query, str) or not 8 <= len(focused_query.strip()) <= 240:
            raise RequirementProposalError("proposal_focused_query_invalid")
        normalized_text = focused_query.casefold()
        if (
            _ANSWER_VALUE_PATTERN.search(focused_query)
            or any(marker in normalized_text for marker in _FORBIDDEN_TEXT)
            or not (_question_tokens(focused_query) & question_tokens)
        ):
            raise RequirementProposalError("proposal_focused_query_unsafe")
        if not isinstance(value_shape, str) or value_shape not in _VALUE_SHAPES:
            raise RequirementProposalError("proposal_value_shape_invalid")
        if not isinstance(groups, list) or not 1 <= len(groups) <= 5:
            raise RequirementProposalError("proposal_marker_groups_invalid")
        normalized_groups: list[tuple[str, ...]] = []
        for group in groups:
            if not isinstance(group, list) or not 1 <= len(group) <= 4:
                raise RequirementProposalError("proposal_marker_group_invalid")
            normalized_group: list[str] = []
            for marker in group:
                if not isinstance(marker, str) or not 2 <= len(marker.strip()) <= 48:
                    raise RequirementProposalError("proposal_marker_invalid")
                normalized = marker.strip().casefold()
                if _ANSWER_VALUE_PATTERN.search(normalized) or any(
                    item in normalized for item in _FORBIDDEN_TEXT
                ):
                    raise RequirementProposalError("proposal_marker_unsafe")
                normalized_group.append(normalized)
            normalized_groups.append(tuple(dict.fromkeys(normalized_group)))
        identities.add(identity)
        slot = RequirementSlot(
            identity=identity,
            focused_query=focused_query.strip(),
            support_marker_groups=tuple(normalized_groups),
            value_shape=value_shape,  # type: ignore[arg-type]
            marker_match_mode="token_overlap",
        )
        # ★ 模型可以提出 aspect，但不能宣称它缺失；本地 Evidence coverage 重算后只保留真缺口。
        if not slot.supported_by(current_evidence):
            slots.append(slot)
    if not slots:
        raise RequirementProposalError("proposal_no_unsupported_requirement")
    return RequirementProposal(
        slots=tuple(slots),
        prompt_fingerprint=prompt_fingerprint,
        response_fingerprint=canonical_hash(raw),
        usage=usage,
    )


class EvidenceAwareRequirementProposer:
    """一次有界模型调用：build prompt → transport → deterministic validate。"""

    def __init__(self, transport: RequirementProposalTransport) -> None:
        self._transport = transport

    def propose(self, *, question: str, current_evidence: tuple[Evidence, ...]) -> RequirementProposal:
        """★ 完成恰好一次 proposal 调用，并在返回前经过本地 schema/coverage 裁决。"""

        prompt, _ = _build_prompt(question=question, evidence=current_evidence)
        before_calls = self._transport.request_count
        before_tokens = self._transport.total_tokens
        try:
            raw = self._transport.complete(
                prompt=prompt,
                system_prompt=(
                    "You are a retrieval requirement planner. Output strict JSON only. "
                    "Never answer the question and never invent exact answer values."
                ),
                node_purpose=PROPOSAL_PURPOSE,
            )
        except LLMGenerationError:
            raise
        usage = ProposalUsage(
            model=self._transport.model,
            calls=self._transport.request_count - before_calls,
            total_tokens=self._transport.total_tokens - before_tokens,
            token_usage_observed=True,
        )
        if usage.calls != 1 or usage.total_tokens < 0:
            raise RequirementProposalError("proposal_usage_invalid")
        try:
            proposal = validate_requirement_proposal(
                raw=raw,
                question=question,
                current_evidence=current_evidence,
                prompt_fingerprint=canonical_hash(prompt),
                usage=usage,
            )
        except RequirementProposalError as exc:
            # 失败 raw 只随异常交给 Probe runner 写 external private artifact；安全投影仍只记 reason。
            exc.prompt = prompt
            exc.raw_response = raw
            exc.usage = usage
            raise
        return RequirementProposal(
            slots=proposal.slots,
            prompt_fingerprint=proposal.prompt_fingerprint,
            response_fingerprint=proposal.response_fingerprint,
            usage=proposal.usage,
            prompt=prompt,
            raw_response=raw,
        )
