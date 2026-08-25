"""M45 external sibling context expansion adapter：SQLite authority → ACL → 新 Evidence。

通用 Enterprise runtime 只提供同一 physical document 的有界 sibling identity；是否把它解释为
recovery action、怎样匹配 typed slot 和怎样计预算，都集中在 Phase 4B diagnostic module，
因此普通产品 RAG、M44 B2 Loop 与 active semantic 默认不会改变。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import re
from typing import Any

from engine.governance import DocumentAuthorizationPolicy, TrustedCaller, authorize_document
from engine.phase4b.rag_diagnostics import ExpansionPreview, RequirementSlot
from engine.rag.catalog import CatalogEntry
from engine.rag.enterprise_runtime import EnterpriseProfileRuntime
from engine.rag.evidence import DocumentContextCoordinates, DocumentEvidencePayload, Evidence, make_document_evidence


@dataclass(frozen=True)
class _AuthorizedSibling:
    """已通过 pre-selection 且属于最小支持组合的私有 sibling。"""

    seed_evidence_id: str
    entry: CatalogEntry
    coordinates: DocumentContextCoordinates
    slot_identities: tuple[str, ...]


class EnterpriseSiblingExpansionAdapter:
    """★ 从已授权 seed 出发搜索同文档 sibling，并对每个新增 unit 重做 ACL 双检。"""

    identity = "phase4b-enterprise-sibling-expansion-v2"

    def __init__(
        self,
        runtime: EnterpriseProfileRuntime,
        *,
        authorization_policy: DocumentAuthorizationPolicy = DocumentAuthorizationPolicy(),
    ) -> None:
        self._runtime = runtime
        self._policy = authorization_policy
        self._entries_by_unit = {
            entry.document_key.removeprefix("enterprise-unit:"): entry
            for entry in runtime.bundle.entries
        }

    @staticmethod
    def _rank_seeds(
        seeds: tuple[Evidence, ...], unsupported_slots: tuple[RequirementSlot, ...]
    ) -> tuple[Evidence, ...]:
        """按 signed requirement 与已授权正文的通用词项重合排序，不读取 gold/title oracle。

        title 是当前已授权 Evidence payload 的普通检索字段，可以参与相关度；这里不接受
        document key、scenario-specific expected ID 或动作后人工 verdict。相同分数保持原始
        retrieval 顺序，使选择可复现。
        """

        stopwords = {
            "a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "use",
            "what", "with", "current", "authoritative", "procedure", "routine",
        }
        query_tokens = {
            token
            for slot in unsupported_slots
            for token in re.findall(r"[a-z0-9][a-z0-9_-]+", slot.focused_query.casefold())
            if token not in stopwords and len(token) > 2
        }

        def score(index_and_seed: tuple[int, Evidence]) -> tuple[int, int]:
            index, seed = index_and_seed
            payload = seed.payload
            if not isinstance(payload, DocumentEvidencePayload):
                return (0, -index)
            title_tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]+", payload.title.casefold()))
            body_tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]+", payload.content.casefold()))
            # 标题只做普通相关度加权；稳定坐标和 document key 从不进入 score。
            relevance = 2 * len(query_tokens & title_tokens) + len(query_tokens & body_tokens)
            # proposal slot 的 focused query 仍可能让“标题很像、正文无关”的文档占满 2-seed
            # 预算。只对显式 token_overlap slot，用模型已经提出且 validator 接受的 marker
            # coverage 作高权重 hint；不读取 gold/ID，也不改变旧 exact 排序。
            proposal_marker_hints = sum(
                slot.marker_match_mode == "token_overlap"
                and slot.markers_supported_by_text(payload.content)
                for slot in unsupported_slots
            )
            relevance += 10 * proposal_marker_hints
            return (relevance, -index)

        ranked = sorted(enumerate(seeds), key=score, reverse=True)
        return tuple(seed for _, seed in ranked)

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
    ) -> tuple[ExpansionPreview, ...]:
        """先授权再扫描 sibling，选择能最大化 coverage 的最小确定性组合。

        单个 unit 常只覆盖 requirement 的一部分，因此判据必须看 ``seed + subset`` 的联合
        正文，不能要求每个 sibling 单独含齐所有 marker。最多 8 个候选、组合大小最多 4，
        closed-world 穷举规模固定且可测试；相同 coverage 时优先更小、再保持距离顺序。
        """

        previews: list[ExpansionPreview] = []
        seen_units: set[str] = set()
        for seed in self._rank_seeds(seeds, unsupported_slots)[:max_seeds]:
            payload = seed.payload
            if not isinstance(payload, DocumentEvidencePayload) or payload.context_coordinates is None:
                continue
            seed_coordinates = payload.context_coordinates
            siblings: list[_AuthorizedSibling] = []
            for unit_identity in self._runtime.context_loader.sibling_unit_identities(
                seed_coordinates, max_units=max_sibling_units_scanned_per_seed,
            ):
                if unit_identity in seen_units:
                    continue
                entry = self._entries_by_unit.get(unit_identity)
                if entry is None or entry.source_key != seed_coordinates.physical_source_identity:
                    continue
                pre_selection = authorize_document(
                    caller=caller,
                    entry=entry,
                    purpose=purpose,
                    phase="pre_selection",
                    policy=self._policy,
                )
                if not pre_selection.allowed:
                    continue
                materialized = self._runtime.context_loader(entry)
                if materialized.coordinates is None:
                    continue
                siblings.append(_AuthorizedSibling(
                    seed_evidence_id=seed.ref.evidence_id,
                    entry=materialized.entry,
                    coordinates=materialized.coordinates,
                    slot_identities=(),
                ))
            best_subset: tuple[_AuthorizedSibling, ...] = ()
            best_supported: tuple[str, ...] = ()
            upper = min(max_added, len(siblings))
            for size in range(1, upper + 1):
                for subset in combinations(siblings, size):
                    text = "\n".join(
                        (payload.content, *(item.entry.content for item in subset))
                    ).casefold()
                    supported = tuple(
                        slot.identity
                        for slot in unsupported_slots
                        if slot.supported_by_text(text)
                    )
                    if len(supported) > len(best_supported):
                        best_subset, best_supported = subset, supported
                # 已覆盖全部 gap 时，当前 size 就是最小组合，无需继续扩大。
                if len(best_supported) == len(unsupported_slots):
                    break
            if best_subset and best_supported:
                chosen = tuple(
                    _AuthorizedSibling(
                        seed_evidence_id=item.seed_evidence_id,
                        entry=item.entry,
                        coordinates=item.coordinates,
                        slot_identities=best_supported,
                    )
                    for item in best_subset
                )
                seen_units.update(item.coordinates.unit_identity for item in chosen)
                previews.append(ExpansionPreview(
                    seed_evidence_id=seed.ref.evidence_id,
                    slot_identities=best_supported,
                    opaque_candidates=chosen,
                ))
        return tuple(previews)

    def preview_forward_continuation(
        self,
        *,
        seeds: tuple[Evidence, ...],
        procedure_slots: tuple[RequirementSlot, ...],
        caller: TrustedCaller,
        purpose: str,
        max_seeds: int,
        max_added: int,
    ) -> tuple[ExpansionPreview, ...]:
        """为 procedure-shaped query 选择同文档紧邻的后续 unit。

        这个 trigger 只证明“selected fragment 不是物理文档末片”，不宣称后续正文一定支持某
        个答案事实。最多看两个相关 seed、每个 seed 只取一个 forward unit，且仍先授权后水化。
        """

        previews: list[ExpansionPreview] = []
        seen_units: set[str] = set()
        for seed in self._rank_seeds(seeds, procedure_slots)[:max_seeds]:
            if sum(len(item.opaque_candidates) for item in previews) >= max_added:
                break
            payload = seed.payload
            if not isinstance(payload, DocumentEvidencePayload) or payload.context_coordinates is None:
                continue
            seed_coordinates = payload.context_coordinates
            unit_identity = self._runtime.context_loader.following_sibling_unit_identity(
                seed_coordinates
            )
            if unit_identity is None or unit_identity in seen_units:
                continue
            entry = self._entries_by_unit.get(unit_identity)
            if entry is None or entry.source_key != seed_coordinates.physical_source_identity:
                continue
            pre_selection = authorize_document(
                caller=caller,
                entry=entry,
                purpose=purpose,
                phase="pre_selection",
                policy=self._policy,
            )
            if not pre_selection.allowed:
                continue
            materialized = self._runtime.context_loader(entry)
            coordinates = materialized.coordinates
            if (
                coordinates is None
                or coordinates.physical_source_identity
                != seed_coordinates.physical_source_identity
                or coordinates.normalized_start < seed_coordinates.normalized_end
            ):
                continue
            seen_units.add(coordinates.unit_identity)
            previews.append(ExpansionPreview(
                seed_evidence_id=seed.ref.evidence_id,
                slot_identities=("procedure_forward_continuation",),
                opaque_candidates=(_AuthorizedSibling(
                    seed_evidence_id=seed.ref.evidence_id,
                    entry=materialized.entry,
                    coordinates=coordinates,
                    slot_identities=("procedure_forward_continuation",),
                ),),
            ))
        return tuple(previews)

    def materialize(
        self,
        *,
        previews: tuple[ExpansionPreview, ...],
        caller: TrustedCaller,
        purpose: str,
        run_id: str,
        max_added: int,
    ) -> tuple[Evidence, ...]:
        """chosen action 后逐项 pre-generation 授权并形成新的 EvidenceRef。"""

        evidence: list[Evidence] = []
        for preview in previews:
            for opaque in preview.opaque_candidates:
                if len(evidence) >= max_added:
                    return tuple(evidence)
                if not isinstance(opaque, _AuthorizedSibling):
                    continue
                pre_selection = authorize_document(
                    caller=caller,
                    entry=opaque.entry,
                    purpose=purpose,
                    phase="pre_selection",
                    policy=self._policy,
                )
                pre_generation = authorize_document(
                    caller=caller,
                    entry=opaque.entry,
                    purpose=purpose,
                    phase="pre_generation",
                    policy=self._policy,
                )
                if not pre_selection.allowed or not pre_generation.allowed:
                    continue
                evidence.append(make_document_evidence(
                    run_id=run_id,
                    release_identity=self._runtime.bundle.release_identity,
                    entry=opaque.entry,
                    purpose=purpose,
                    authorization=pre_selection,
                    runtime_ref=f"context-expansion:{self.identity}",
                    context_coordinates=opaque.coordinates,
                ))
        return tuple(evidence)

    def safe_projection(self) -> dict[str, Any]:
        """只暴露 adapter/profile identity，不投影相邻正文或 unit identity。"""

        return {
            "identity": self.identity,
            "profile_identity": self._runtime.manifest.profile_identity,
            "unit_recipe_identity": self._runtime.manifest.unit_recipe_identity,
        }
