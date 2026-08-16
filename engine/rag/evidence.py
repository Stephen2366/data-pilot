"""Phase 4 typed Evidence、四阶段账本与 citation 完整性校验。

Evidence 的完整对象只在受控运行时使用；长期审计和未来公开响应只能通过本模块提供的投影。
这样可以防止 ``docs_used: list[dict]`` 一类开放结构反向冒充已授权、已入模的事实。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Literal, Mapping

from engine.governance import AuthorizationDecision, document_safe_ref
from engine.rag.catalog import CatalogEntry, KNOWN_PURPOSES

EvidenceKind = Literal["document", "sql"]
EvidenceStage = Literal["candidate", "selected", "generation_visible", "cited"]
STAGE_ORDER: tuple[EvidenceStage, ...] = ("candidate", "selected", "generation_visible", "cited")


class EvidenceContractError(ValueError):
    """Evidence/citation 合同失败；公开层只应显示稳定 reason code。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _identity(namespace: str, *parts: str) -> str:
    """从稳定运行事实生成代码控制的 Evidence/citation identity。"""

    value = "\0".join((namespace, *parts)).encode("utf-8")
    return f"{namespace}:{sha256(value).hexdigest()}"


def _required_text(name: str, value: str) -> str:
    """拒绝会让 Evidence 无法回查的空文本字段。"""

    normalized = value.strip()
    if not normalized:
        raise EvidenceContractError("evidence_invalid", f"{name} 不能为空")
    return normalized


@dataclass(frozen=True)
class EvidenceRef:
    """可长期保存且不含正文的 Evidence 定位坐标。"""

    run_id: str
    evidence_id: str
    evidence_kind: EvidenceKind
    authority_identity: str
    revision: str
    content_identity: str
    anchor: str

    def audit_projection(self) -> dict[str, str]:
        """返回不含正文的稳定 Evidence reference。"""

        return asdict(self)


@dataclass(frozen=True)
class DocumentContextCoordinates:
    """大 corpus Evidence 的 document → unit → normalized anchor 坐标。"""

    source_type: str
    logical_document_id: str
    physical_source_identity: str
    unit_identity: str
    normalized_start: int
    normalized_end: int


@dataclass(frozen=True)
class DocumentEvidencePayload:
    """内部文档 Evidence；包含当前消费者真正可用的受控正文。"""

    release_identity: str
    document_key: str
    revision: str
    title: str
    knowledge_type: str
    anchor: str
    content: str
    context_coordinates: DocumentContextCoordinates | None = None


@dataclass(frozen=True)
class SQLEvidencePayload:
    """已通过 SQL Guard 的查询与结果身份。"""

    guarded_sql: str
    columns: tuple[str, ...]
    rows_count: int
    result_fingerprint: str
    queried_at: str
    database_identity: str
    runtime_identity: str
    safe_result_view: tuple[tuple[Any, ...], ...] = ()


@dataclass(frozen=True)
class Evidence:
    """稳定公共外壳加一种 typed payload。"""

    ref: EvidenceRef
    allowed_uses: tuple[str, ...]
    authorization_ref: str
    runtime_ref: str
    payload: DocumentEvidencePayload | SQLEvidencePayload

    def safe_projection(self) -> dict[str, Any]:
        """默认长期投影不包含标题、正文、SQL rows 或授权内部原因。"""

        return {
            "ref": self.ref.audit_projection(),
            "allowed_uses": list(self.allowed_uses),
            "authorization_ref": self.authorization_ref,
            "runtime_ref": self.runtime_ref,
        }


def make_document_evidence(
    *,
    run_id: str,
    release_identity: str,
    entry: CatalogEntry,
    purpose: str,
    authorization: AuthorizationDecision,
    runtime_ref: str,
    context_coordinates: DocumentContextCoordinates | None = None,
) -> Evidence:
    """仅由 active release entry 和成功的 pre-selection decision 构造候选 Evidence。"""

    if not authorization.allowed or authorization.phase != "pre_selection":
        raise EvidenceContractError("evidence_unauthorized", "Document Evidence 缺少候选阶段授权")
    if (
        authorization.allowed_purpose != purpose
        or purpose not in entry.purposes
        or authorization.evidence_safe_ref != document_safe_ref(entry)
    ):
        raise EvidenceContractError("evidence_purpose_invalid", "Evidence 用途与授权或原件不一致")
    if entry.status != "active":
        raise EvidenceContractError("evidence_revision_unavailable", "非 active revision 不能构造新 Evidence")
    if purpose not in KNOWN_PURPOSES:
        raise EvidenceContractError("evidence_purpose_invalid", "未知 Evidence 用途")
    run_id = _required_text("run_id", run_id)
    release_identity = _required_text("release_identity", release_identity)
    evidence_id = _identity(
        "evidence", run_id, release_identity, entry.document_key, entry.revision, entry.anchor, purpose
    )
    ref = EvidenceRef(
        run_id=run_id,
        evidence_id=evidence_id,
        evidence_kind="document",
        authority_identity=entry.authority_ref,
        revision=entry.revision,
        content_identity=entry.content_identity,
        anchor=entry.anchor,
    )
    return Evidence(
        ref=ref,
        allowed_uses=(purpose,),
        authorization_ref=_identity(
            "authorization", authorization.policy_identity, authorization.caller_safe_ref, authorization.evidence_safe_ref
        ),
        runtime_ref=_required_text("runtime_ref", runtime_ref),
        payload=DocumentEvidencePayload(
            release_identity=release_identity,
            document_key=entry.document_key,
            revision=entry.revision,
            title=entry.title,
            knowledge_type=entry.knowledge_type,
            anchor=entry.anchor,
            content=entry.content,
            context_coordinates=context_coordinates,
        ),
    )


def make_sql_evidence(
    *,
    run_id: str,
    guarded_sql: str,
    columns: tuple[str, ...],
    rows_count: int,
    result_fingerprint: str,
    queried_at: str,
    database_identity: str,
    runtime_identity: str,
    safe_result_view: tuple[tuple[Any, ...], ...] = (),
) -> Evidence:
    """构造已通过 SQL Guard 的 SQL Evidence；M31 只冻结类型，不接现有 API。"""

    run_id = _required_text("run_id", run_id)
    sql = _required_text("guarded_sql", guarded_sql)
    if not sql.lower().startswith(("select", "with")) or rows_count < 0:
        raise EvidenceContractError("sql_evidence_invalid", "SQL Evidence 必须是已 Guard 的只读查询结果")
    result_fingerprint = _required_text("result_fingerprint", result_fingerprint)
    ref = EvidenceRef(
        run_id=run_id,
        evidence_id=_identity("evidence", run_id, sql, result_fingerprint, runtime_identity),
        evidence_kind="sql",
        authority_identity=_required_text("database_identity", database_identity),
        revision=_required_text("queried_at", queried_at),
        content_identity=result_fingerprint,
        anchor="sql-result",
    )
    return Evidence(
        ref=ref,
        allowed_uses=("answer_evidence",),
        authorization_ref="sql-guard:passed",
        runtime_ref=_required_text("runtime_identity", runtime_identity),
        payload=SQLEvidencePayload(
            guarded_sql=sql,
            columns=tuple(columns),
            rows_count=rows_count,
            result_fingerprint=result_fingerprint,
            queried_at=queried_at,
            database_identity=database_identity,
            runtime_identity=runtime_identity,
            safe_result_view=tuple(tuple(row) for row in safe_result_view),
        ),
    )


@dataclass(frozen=True)
class EvidenceLedger:
    """一次 run 的不可变阶段账本；每次迁移返回新账本，旧事实不会被覆盖。"""

    run_id: str
    evidence: tuple[Evidence, ...] = ()
    stages: tuple[tuple[str, EvidenceStage], ...] = ()

    @classmethod
    def from_candidates(cls, *, run_id: str, evidence: tuple[Evidence, ...]) -> "EvidenceLedger":
        """建立同轮、无重复的 candidate 初始账本。"""

        ids = [item.ref.evidence_id for item in evidence]
        if len(ids) != len(set(ids)) or any(item.ref.run_id != run_id for item in evidence):
            raise EvidenceContractError("evidence_run_mismatch", "候选 Evidence 必须同轮且 identity 唯一")
        return cls(run_id=run_id, evidence=evidence, stages=tuple((item_id, "candidate") for item_id in ids))

    def stage_of(self, evidence_id: str) -> EvidenceStage:
        """查询当前阶段；未知 identity 失败关闭。"""

        try:
            return dict(self.stages)[evidence_id]
        except KeyError as exc:
            raise EvidenceContractError("evidence_unknown", "未知 Evidence identity") from exc

    def evidence_by_id(self, evidence_id: str) -> Evidence:
        """按代码分配的 identity 取得完整内部 Evidence。"""

        for item in self.evidence:
            if item.ref.evidence_id == evidence_id:
                return item
        raise EvidenceContractError("evidence_unknown", "未知 Evidence identity")

    def transition(
        self,
        *,
        evidence_ids: tuple[str, ...],
        to_stage: EvidenceStage,
        generation_authorizations: Mapping[str, AuthorizationDecision] | None = None,
    ) -> "EvidenceLedger":
        """只允许单步正向迁移，并在入模前强制二次授权。"""

        if len(evidence_ids) != len(set(evidence_ids)):
            raise EvidenceContractError("evidence_transition_invalid", "迁移列表包含重复 identity")
        updated = dict(self.stages)
        target_index = STAGE_ORDER.index(to_stage)
        for evidence_id in evidence_ids:
            current = self.stage_of(evidence_id)
            if STAGE_ORDER.index(current) + 1 != target_index:
                raise EvidenceContractError("evidence_transition_invalid", f"不允许 {current} -> {to_stage}")
            if to_stage == "generation_visible":
                decision = (generation_authorizations or {}).get(evidence_id)
                item = self.evidence_by_id(evidence_id)
                if (
                    item.ref.evidence_kind == "document"
                    and (decision is None or not decision.allowed or decision.phase != "pre_generation")
                ):
                    raise EvidenceContractError("evidence_unauthorized", "入模前必须重新授权")
            updated[evidence_id] = to_stage
        stable_stages = tuple((item.ref.evidence_id, updated[item.ref.evidence_id]) for item in self.evidence)
        return EvidenceLedger(run_id=self.run_id, evidence=self.evidence, stages=stable_stages)

    def safe_projection(self) -> dict[str, Any]:
        """投影长期可保存的 refs/hash/stage，不包含正文。"""

        return {
            "run_ref": _identity("run", self.run_id),
            "evidence": [item.safe_projection() for item in self.evidence],
            "stages": [{"evidence_id": item_id, "stage": stage} for item_id, stage in self.stages],
        }


@dataclass(frozen=True)
class CitationSlot:
    """代码为某个 claim 预分配的 citation 位置。"""

    run_id: str
    slot_id: str
    claim_ref: str


@dataclass(frozen=True)
class CitationDraft:
    """等待确定性校验的 claim-to-Evidence 引用提案。"""

    run_id: str
    slot_id: str
    claim_ref: str
    evidence_id: str
    anchor: str


@dataclass(frozen=True)
class ValidatedCitation:
    """已通过同轮、阶段、ACL、revision 与 anchor 校验的引用。"""

    slot_id: str
    claim_ref: str
    evidence_ref: EvidenceRef


def allocate_citation_slot(*, run_id: str, claim_ref: str, ordinal: int) -> CitationSlot:
    """slot 只能由代码依据本轮 claim 分配；模型不能自造任意 ID。"""

    if ordinal < 1:
        raise EvidenceContractError("citation_slot_invalid", "citation ordinal 必须从 1 开始")
    run_id = _required_text("run_id", run_id)
    claim_ref = _required_text("claim_ref", claim_ref)
    return CitationSlot(
        run_id=run_id,
        slot_id=_identity("citation-slot", run_id, claim_ref, str(ordinal)),
        claim_ref=claim_ref,
    )


def validate_citations(
    *,
    ledger: EvidenceLedger,
    slots: tuple[CitationSlot, ...],
    drafts: tuple[CitationDraft, ...],
    current_entries: Mapping[tuple[str, str], CatalogEntry],
    generation_authorizations: Mapping[str, AuthorizationDecision],
) -> tuple[tuple[ValidatedCitation, ...], EvidenceLedger]:
    """验证 identity/stage/run/revision/anchor/ACL；任一失败不返回部分 citation。"""

    slot_map = {slot.slot_id: slot for slot in slots}
    if len(slot_map) != len(slots) or len(drafts) != len({draft.slot_id for draft in drafts}):
        raise EvidenceContractError("citation_invalid", "citation slot 重复")
    validated: list[ValidatedCitation] = []
    cited_ids: list[str] = []
    try:
        for draft in drafts:
            slot = slot_map[draft.slot_id]
            if draft.run_id != ledger.run_id or slot.run_id != ledger.run_id or draft.claim_ref != slot.claim_ref:
                raise KeyError("run/claim mismatch")
            if ledger.stage_of(draft.evidence_id) != "generation_visible":
                raise KeyError("not generation visible")
            item = ledger.evidence_by_id(draft.evidence_id)
            if item.ref.anchor != draft.anchor:
                raise KeyError("anchor mismatch")
            decision = generation_authorizations.get(draft.evidence_id)
            if item.ref.evidence_kind == "document":
                payload = item.payload
                if not isinstance(payload, DocumentEvidencePayload):
                    raise KeyError("payload mismatch")
                current = current_entries[(payload.document_key, payload.revision)]
                if (
                    current.status != "active"
                    or current.content_identity != item.ref.content_identity
                    or current.anchor != item.ref.anchor
                    or decision is None
                    or not decision.allowed
                    or decision.phase != "pre_generation"
                    or decision.allowed_purpose not in item.allowed_uses
                    or decision.evidence_safe_ref != document_safe_ref(current)
                ):
                    raise KeyError("revision/authorization mismatch")
            validated.append(ValidatedCitation(slot.slot_id, slot.claim_ref, item.ref))
            cited_ids.append(item.ref.evidence_id)
    except (KeyError, EvidenceContractError) as exc:
        raise EvidenceContractError("citation_invalid", "citation 未通过完整性校验") from exc
    # 多个 claim 合法复用同一份入模 Evidence；阶段只需推进一次，citation 记录仍逐条保留。
    unique_cited_ids = tuple(dict.fromkeys(cited_ids))
    return tuple(validated), ledger.transition(evidence_ids=unique_cited_ids, to_stage="cited")
