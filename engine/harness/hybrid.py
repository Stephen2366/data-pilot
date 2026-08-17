"""M38 保守 Hybrid 的本地确定性合成与 claim-to-Evidence 校验。

本模块不调用模型，也不碰数据库/网络。它只接收已经经过 SQL Guard、RAG Shared Gate 的同轮
typed Evidence，并把受控 operator 转成可复核的 claim。这样“如何写一句话”不会偷走 ACL、
required branch、conflict 或 citation 的裁决权。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from engine.harness.contracts import BranchResult, HarnessContractError, HybridPlan
from engine.rag.evidence import DocumentEvidencePayload, Evidence, SQLEvidencePayload


class HybridSynthesisError(ValueError):
    """本地 Synthesizer 返回非法草稿或无法安全合成时使用的内部错误。"""


@dataclass(frozen=True)
class HybridClaimDraft:
    """结构化草稿：文本与绑定的 Evidence identity 必须一起交给 validator。"""

    claim_ref: str
    text: str
    evidence_ids: tuple[str, ...]
    kind: Literal["cross_source", "sql_partial", "rag_partial"]


class HybridSynthesizer(Protocol):
    """正式 adapter seam；未来远程 adapter 也必须先满足相同的本地 validator 合同。"""

    identity: str

    def compose(self, *, plan: HybridPlan, branches: tuple[BranchResult, ...]) -> tuple[HybridClaimDraft, ...]:
        """只从 Gate 可见 typed Evidence 生成 closed-world operator 的草稿。"""


class DeterministicHybridSynthesizer:
    """★ M38 的正式默认 Synthesizer：可复现的受控 operator，不是临时 mock。"""

    identity = "hybrid-deterministic-structured-v1"

    def compose(self, *, plan: HybridPlan, branches: tuple[BranchResult, ...]) -> tuple[HybridClaimDraft, ...]:
        """按成功分支生成跨来源或已声明的独立 partial 草稿。"""

        branch_map = {branch.branch: branch for branch in branches}
        if set(branch_map) != {"sql", "rag"}:
            raise HybridSynthesisError("Hybrid 必须有且只有 SQL/RAG branch")
        sql_ready, rag_ready = branch_map["sql"].evidence_ready, branch_map["rag"].evidence_ready
        if sql_ready and rag_ready:
            sql_evidence = _single_kind(branch_map["sql"], "sql")
            document_evidence = _single_kind(branch_map["rag"], "document")
            sql_text = _sql_fact(sql_evidence)
            document_text = _document_fact(document_evidence)
            return (
                HybridClaimDraft(
                    claim_ref=f"{plan.identity}:cross-source:1",
                    text=f"数据事实：{sql_text}\n规则依据：{document_text}\n以上结论同时基于本轮数据与当前规则证据。",
                    evidence_ids=(sql_evidence.ref.evidence_id, document_evidence.ref.evidence_id),
                    kind="cross_source",
                ),
            )
        if sql_ready:
            sql_evidence = _single_kind(branch_map["sql"], "sql")
            return (
                HybridClaimDraft(
                    claim_ref=f"{plan.identity}:sql-partial:1",
                    text=f"当前可独立确认的数据事实：{_sql_fact(sql_evidence)}。尚不能形成跨来源结论。",
                    evidence_ids=(sql_evidence.ref.evidence_id,),
                    kind="sql_partial",
                ),
            )
        if rag_ready:
            document_evidence = _single_kind(branch_map["rag"], "document")
            return (
                HybridClaimDraft(
                    claim_ref=f"{plan.identity}:rag-partial:1",
                    text=f"当前可独立说明的规则依据：{_document_fact(document_evidence)}。尚不能确认其在当前数据中的表现。",
                    evidence_ids=(document_evidence.ref.evidence_id,),
                    kind="rag_partial",
                ),
            )
        return ()


def validate_hybrid_claims(
    *, plan: HybridPlan, branches: tuple[BranchResult, ...], drafts: tuple[HybridClaimDraft, ...]
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """★ 校验 run、kind、stage 与 required binding，并产生唯一允许公开的 claim/citation 投影。"""

    evidence = {item.ref.evidence_id: item for branch in branches for item in branch.observation.raw_evidence}
    if not drafts:
        return (), ()
    claims: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    for draft in drafts:
        if not draft.claim_ref.startswith(f"{plan.identity}:") or not draft.text.strip():
            raise HybridSynthesisError("Hybrid claim identity 或文本非法")
        bound = tuple(evidence.get(item_id) for item_id in draft.evidence_ids)
        if len(bound) != len(draft.evidence_ids) or any(item is None for item in bound):
            raise HybridSynthesisError("Hybrid claim 引用了未知 Evidence")
        items = tuple(item for item in bound if item is not None)
        if len({item.ref.run_id for item in items}) != 1:
            raise HybridSynthesisError("Hybrid claim Evidence 必须同轮")
        kinds = {item.ref.evidence_kind for item in items}
        if draft.kind == "cross_source" and kinds != {"sql", "document"}:
            raise HybridSynthesisError("跨来源 claim 必须同时绑定 SQL 与 Document Evidence")
        if draft.kind == "sql_partial" and kinds != {"sql"}:
            raise HybridSynthesisError("SQL partial 只能绑定 SQL Evidence")
        if draft.kind == "rag_partial" and kinds != {"document"}:
            raise HybridSynthesisError("RAG partial 只能绑定 Document Evidence")
        for item in items:
            branch = next(branch for branch in branches if item in branch.observation.raw_evidence)
            ledger = branch.observation.evidence_ledger
            if ledger is None or ledger.stage_of(item.ref.evidence_id) != "generation_visible":
                raise HybridSynthesisError("Hybrid citation 只能使用本轮 Gate 可见 Evidence")
        citation_ids: list[str] = []
        for ordinal, item in enumerate(items, start=1):
            citation_id = f"{draft.claim_ref}:citation:{ordinal}"
            citation_ids.append(citation_id)
            citations.append(_citation_view(citation_id=citation_id, claim_ref=draft.claim_ref, evidence=item))
        claims.append({"claim_ref": draft.claim_ref, "text": draft.text, "citation_ids": citation_ids, "kind": draft.kind})
    return tuple(claims), tuple(citations)


def build_safe_partial_drafts(*, plan: HybridPlan, branches: tuple[BranchResult, ...]) -> tuple[HybridClaimDraft, ...]:
    """Synthesizer 不可用时的独立安全降级：只发布单支已证明事实，永不重跑 Tool。"""

    branch_map = {branch.branch: branch for branch in branches}
    if branch_map.get("sql") and branch_map["sql"].evidence_ready:
        evidence = _single_kind(branch_map["sql"], "sql")
        return (
            HybridClaimDraft(
                claim_ref=f"{plan.identity}:synth-fallback-sql:1",
                text=f"当前可独立确认的数据事实：{_sql_fact(evidence)}。合成器不可用，未形成跨来源结论。",
                evidence_ids=(evidence.ref.evidence_id,),
                kind="sql_partial",
            ),
        )
    if branch_map.get("rag") and branch_map["rag"].evidence_ready:
        evidence = _single_kind(branch_map["rag"], "document")
        return (
            HybridClaimDraft(
                claim_ref=f"{plan.identity}:synth-fallback-rag:1",
                text=f"当前可独立说明的规则依据：{_document_fact(evidence)}。合成器不可用，未形成跨来源结论。",
                evidence_ids=(evidence.ref.evidence_id,),
                kind="rag_partial",
            ),
        )
    return ()


def _single_kind(branch: BranchResult, kind: Literal["sql", "document"]) -> Evidence:
    """受控 operators 只消费每支已进入 context 的第一份对应 Evidence，避免隐式扩预算。"""

    matches = [item for item in branch.observation.raw_evidence if item.ref.evidence_kind == kind]
    if not matches:
        raise HybridSynthesisError(f"{branch.branch} branch 缺少 {kind} Evidence")
    return matches[0]


def _sql_fact(evidence: Evidence) -> str:
    """从安全 result view 做确定性展示；不把未经 Guard 的 SQL 或任意对象序列化成答案。"""

    if not isinstance(evidence.payload, SQLEvidencePayload):
        raise HybridSynthesisError("SQL Evidence payload 类型错误")
    payload = evidence.payload
    if not payload.safe_result_view:
        return "查询未返回记录"
    row = payload.safe_result_view[0]
    fields = "，".join(f"{column}={value}" for column, value in zip(payload.columns, row, strict=True))
    return f"{fields}（本轮结果共 {payload.rows_count} 行）"


def _document_fact(evidence: Evidence) -> str:
    """选择第一条非空原文行作为可审计规则摘录；正文不会进入公开 citation/trace。"""

    if not isinstance(evidence.payload, DocumentEvidencePayload):
        raise HybridSynthesisError("Document Evidence payload 类型错误")
    for line in evidence.payload.content.splitlines():
        normalized = line.strip().lstrip("#-• ")
        if normalized:
            return normalized
    raise HybridSynthesisError("Document Evidence 正文为空")


def _citation_view(*, citation_id: str, claim_ref: str, evidence: Evidence) -> dict[str, Any]:
    """把两类 Evidence 变成最小可回查 citation，禁止向 API/Trace 放入正文或完整 rows。"""

    ref = evidence.ref
    if ref.evidence_kind == "sql":
        payload = evidence.payload
        if not isinstance(payload, SQLEvidencePayload):
            raise HarnessContractError("SQL citation payload 类型错误")
        return {
            "citation_id": citation_id,
            "claim_ref": claim_ref,
            "source_kind": "sql",
            "query_ref": ref.evidence_id,
            "result_identity": payload.result_fingerprint,
            "anchor": ref.anchor,
        }
    payload = evidence.payload
    if not isinstance(payload, DocumentEvidencePayload):
        raise HarnessContractError("Document citation payload 类型错误")
    return {
        "citation_id": citation_id,
        "claim_ref": claim_ref,
        "source_kind": "document",
        "title": payload.title,
        "revision": payload.revision,
        "anchor": ref.anchor,
        "authority_ref": ref.authority_identity,
    }
