"""M34 EnterpriseRAG external profile 到现有 Knowledge/Answer 合同的运行时适配。

大语料的 catalog 只常驻 unit metadata，正文仍留在项目外 SQLite。Knowledge Tool 完成
pre-selection ACL 和检索后，``context_loader`` 才读取命中的少量正文。这样 M31–M33 的
授权、Evidence、Gate、citation 合同都原样生效，又不会把 13.9 万段正文复制进 release JSON。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from threading import RLock
from types import MappingProxyType
from typing import Mapping, Protocol

from engine.rag.answer_flow import RAGAnswerFlow
from engine.rag.catalog import CatalogEntry
from engine.rag.enterprise_profile import (
    ExternalProfileManifest,
    ExternalProfilePointer,
    load_active_external_profile,
    verify_external_profile,
)
from engine.rag.evidence import DocumentContextCoordinates
from engine.rag.knowledge_tool import KnowledgeTool, MaterializedDocumentContext
from engine.rag.retrieval import (
    RetrievalAdapterError,
    RetrievalBatch,
    RetrievalMatch,
    query_fingerprint,
)

ENTERPRISE_ADAPTER_IDENTITY = "knowledge-enterprise-sqlite-lexical-v1"
ENTERPRISE_RETRIEVAL_RECIPE = "fts5-unicode61-or-bm25-dedup-physical-v1"
ENTERPRISE_DOCUMENT_KEY_PREFIX = "enterprise-unit:"
_QUERY_TOKEN = re.compile(r"[A-Za-z0-9_]+")


class _Lock(Protocol):
    """RLock 的最小 context-manager 形状，便于隔离测试注入。"""

    def __enter__(self) -> object: ...
    def __exit__(self, *args: object) -> None: ...


@dataclass(frozen=True)
class EnterpriseProfileSelection:
    """显式 candidate 或 benchmark active pointer 的最小选择事实。"""

    profile_identity: str
    lifecycle_status: str
    pointer_identity: str | None = None


@dataclass(frozen=True)
class EnterpriseProfileBundle:
    """满足 Knowledge/AnswerFlow 所需的只读 bundle view，不内嵌正文。"""

    release_identity: str
    corpus_identity: str
    authorization_policy_identity: str
    outbound_policy_identity: str
    entries: tuple[CatalogEntry, ...]
    entry_index: Mapping[tuple[str, str], CatalogEntry]
    dataset_identity: str
    question_set_identity: str
    parser_identity: str
    unit_recipe_identity: str
    index_identity: str


def _document_key(unit_identity: str) -> str:
    """每个 unit 都必须有独立 key，否则旧 citation map 会把同文档切片互相覆盖。"""

    return f"{ENTERPRISE_DOCUMENT_KEY_PREFIX}{unit_identity}"


def _unit_identity(document_key: str) -> str:
    if not document_key.startswith(ENTERPRISE_DOCUMENT_KEY_PREFIX):
        raise RetrievalAdapterError("retrieval_context_invalid", "不是 Enterprise unit key")
    identity = document_key[len(ENTERPRISE_DOCUMENT_KEY_PREFIX) :]
    if not identity:
        raise RetrievalAdapterError("retrieval_context_invalid", "unit identity 为空")
    return identity


def _open_read_only(database_path: Path, *, allow_cross_thread: bool = False) -> sqlite3.Connection:
    """使用 SQLite URI 的只读模式；跨线程仅供显式 TestClient Eval runtime。"""

    connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro",
        uri=True,
        check_same_thread=not allow_cross_thread,
    )
    connection.row_factory = sqlite3.Row
    return connection


def _load_bundle(
    connection: sqlite3.Connection, manifest: ExternalProfileManifest
) -> EnterpriseProfileBundle:
    """只加载 metadata；139k unit 的正文继续留在 SQLite。"""

    rows = connection.execute(
        """
        SELECT u.unit_identity, u.physical_source_identity, u.source_type, u.title,
               u.document_revision, u.anchor, u.content_sha256, d.relative_path
        FROM units AS u
        JOIN documents AS d
          ON d.physical_source_identity = u.physical_source_identity
        ORDER BY u.row_id ASC
        """
    ).fetchall()
    entries = tuple(
        CatalogEntry(
            document_key=_document_key(str(row["unit_identity"])),
            revision=str(row["document_revision"]),
            authority_ref=(
                f"enterprise-rag-bench/{manifest.dataset_identity}/"
                f"{row['relative_path']}#{row['anchor']}"
            ),
            source_kind=str(row["source_type"]),
            source_key=str(row["physical_source_identity"]),
            title=str(row["title"]),
            knowledge_type="enterprise_benchmark_document",
            status="active",
            anchor=str(row["anchor"]),
            data_class="public_benchmark_document",
            purposes=("answer_evidence", "generation_context"),
            public=True,
            allowed_roles=frozenset(),
            content="",
            content_identity=str(row["content_sha256"]),
        )
        for row in rows
    )
    if len(entries) != manifest.unit_count:
        raise RetrievalAdapterError("retrieval_profile_invalid", "runtime metadata 数量漂移")
    index = {(entry.document_key, entry.revision): entry for entry in entries}
    if len(index) != len(entries):
        raise RetrievalAdapterError("retrieval_profile_invalid", "unit citation identity 冲突")
    return EnterpriseProfileBundle(
        release_identity=manifest.profile_identity,
        corpus_identity=manifest.corpus_identity,
        authorization_policy_identity=manifest.authorization_policy_identity,
        outbound_policy_identity=manifest.outbound_policy_identity,
        entries=entries,
        entry_index=MappingProxyType(index),
        dataset_identity=manifest.dataset_identity,
        question_set_identity=manifest.question_set_identity,
        parser_identity=manifest.parser_identity,
        unit_recipe_identity=manifest.unit_recipe_identity,
        index_identity=manifest.index_identity,
    )


class EnterpriseSqliteRetrievalAdapter:
    """在已授权 metadata 集合中查询 FTS，并按物理文档去重。"""

    identity = ENTERPRISE_ADAPTER_IDENTITY
    recipe_identity = ENTERPRISE_RETRIEVAL_RECIPE

    def __init__(self, connection: sqlite3.Connection, *, connection_lock: _Lock | None = None) -> None:
        self._connection = connection
        self._connection_lock = connection_lock or RLock()

    def retrieve(
        self,
        *,
        question: str,
        confirmed_conditions: tuple[str, ...] = (),
        entries: tuple[CatalogEntry, ...],
        limit: int,
    ) -> RetrievalBatch:
        if limit < 1:
            raise RetrievalAdapterError("retrieval_budget_invalid", "limit 必须为正整数")
        if not question.strip():
            raise RetrievalAdapterError("retrieval_query_invalid", "question 不能为空")
        fingerprint = query_fingerprint(question, confirmed_conditions)
        if not entries:
            return RetrievalBatch(self.identity, self.recipe_identity, fingerprint, ())

        allowed: dict[str, CatalogEntry] = {}
        for entry in entries:
            unit_identity = _unit_identity(entry.document_key)
            if unit_identity in allowed:
                raise RetrievalAdapterError("retrieval_entry_duplicate", "重复 unit identity")
            allowed[unit_identity] = entry

        query_text = "\n".join((question, *confirmed_conditions))
        tokens = list(
            dict.fromkeys(
                token.lower()
                for token in _QUERY_TOKEN.findall(query_text)
                if len(token) > 1
            )
        )
        if not tokens:
            return RetrievalBatch(self.identity, self.recipe_identity, fingerprint, ())
        expression = " OR ".join(f'"{token}"' for token in tokens)
        scan_limit = max(500, limit * 50)
        try:
            # ★ check_same_thread=False 只是允许跨线程使用，不代表同一 connection 上的多次
            # cursor 操作应该交错；一把短锁让共享 lifespan runtime 保持只读且可预测。
            with self._connection_lock:
                rows = self._connection.execute(
                    """
                    SELECT u.unit_identity, u.physical_source_identity,
                           bm25(units_fts) AS raw_score
                    FROM units_fts
                    JOIN units AS u ON u.row_id = units_fts.rowid
                    WHERE units_fts MATCH ?
                    ORDER BY raw_score ASC, u.unit_identity ASC
                    LIMIT ?
                    """,
                    (expression, scan_limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise RetrievalAdapterError("retrieval_backend_unavailable", str(exc)) from exc

        selected: list[tuple[CatalogEntry, float]] = []
        seen_physical: set[str] = set()
        for row in rows:
            entry = allowed.get(str(row["unit_identity"]))
            if entry is None or entry.source_key in seen_physical:
                continue
            seen_physical.add(entry.source_key)
            # FTS5 bm25 越小越好，通常为负数；Tool 合同要求正向、有限 score。
            score = max(-float(row["raw_score"]), 1e-12)
            selected.append((entry, score))
            if len(selected) >= limit:
                break
        matches = tuple(
            RetrievalMatch(
                document_key=entry.document_key,
                revision=entry.revision,
                content_identity=entry.content_identity,
                anchor=entry.anchor,
                score=score,
                rank=rank,
            )
            for rank, (entry, score) in enumerate(selected, start=1)
        )
        return RetrievalBatch(self.identity, self.recipe_identity, fingerprint, matches)


class EnterpriseContextLoader:
    """只在 unit 已通过 pre-selection 且真正命中后，加载受控正文和回查坐标。"""

    def __init__(self, connection: sqlite3.Connection, *, connection_lock: _Lock | None = None) -> None:
        self._connection = connection
        self._connection_lock = connection_lock or RLock()

    def __call__(self, entry: CatalogEntry) -> MaterializedDocumentContext:
        unit_identity = _unit_identity(entry.document_key)
        try:
            with self._connection_lock:
                row = self._connection.execute(
                    """
                    SELECT unit_identity, physical_source_identity, logical_document_id,
                           source_type, document_revision, normalized_start, normalized_end,
                           anchor, content_sha256, content
                    FROM units WHERE unit_identity = ?
                    """,
                    (unit_identity,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise RetrievalAdapterError("retrieval_context_unavailable", str(exc)) from exc
        if row is None:
            raise RetrievalAdapterError("retrieval_context_invalid", "unit 不存在")
        content = str(row["content"])
        if (
            str(row["document_revision"]) != entry.revision
            or str(row["anchor"]) != entry.anchor
            or str(row["content_sha256"]) != entry.content_identity
            or sha256(content.encode("utf-8")).hexdigest() != entry.content_identity
        ):
            raise RetrievalAdapterError("retrieval_context_invalid", "unit identity/content 漂移")
        coordinates = DocumentContextCoordinates(
            source_type=str(row["source_type"]),
            logical_document_id=str(row["logical_document_id"]),
            physical_source_identity=str(row["physical_source_identity"]),
            unit_identity=str(row["unit_identity"]),
            normalized_start=int(row["normalized_start"]),
            normalized_end=int(row["normalized_end"]),
        )
        if coordinates.normalized_end <= coordinates.normalized_start:
            raise RetrievalAdapterError("retrieval_context_invalid", "unit offsets 非法")
        return MaterializedDocumentContext(
            entry=replace(entry, content=content),
            coordinates=coordinates,
        )

    def sibling_unit_identities(
        self,
        coordinates: DocumentContextCoordinates,
        *,
        max_units: int = 8,
    ) -> tuple[str, ...]:
        """按离 seed 的距离返回同一 physical document 内至多 8 个 sibling identity。

        ★ 这里只返回 identity，不提前加载正文。M45 adapter 会先把 identity 回到同一 bundle、
        执行 pre-selection ACL，再调用本 loader 水化；“同文档”不等于“有权读取”。距离相同
        时前一个 unit 先于后一个，保证跨运行顺序稳定；不返回 seed 自身。
        """

        if not 1 <= max_units <= 8:
            raise RetrievalAdapterError("retrieval_context_invalid", "sibling scan 上限必须在 1..8")
        try:
            with self._connection_lock:
                rows = self._connection.execute(
                    """
                    SELECT unit_identity, normalized_start, normalized_end
                    FROM units
                    WHERE physical_source_identity = ?
                    ORDER BY normalized_start ASC, normalized_end ASC, unit_identity ASC
                    """,
                    (coordinates.physical_source_identity,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise RetrievalAdapterError("retrieval_context_unavailable", str(exc)) from exc
        identities = [str(row["unit_identity"]) for row in rows]
        try:
            index = identities.index(coordinates.unit_identity)
        except ValueError as exc:
            raise RetrievalAdapterError("retrieval_context_invalid", "seed unit 不属于当前 physical document") from exc
        siblings: list[str] = []
        distance = 1
        while len(siblings) < max_units and (index - distance >= 0 or index + distance < len(identities)):
            if index - distance >= 0:
                siblings.append(identities[index - distance])
                if len(siblings) >= max_units:
                    break
            if index + distance < len(identities):
                siblings.append(identities[index + distance])
            distance += 1
        return tuple(siblings[:max_units])

    def following_sibling_unit_identity(
        self, coordinates: DocumentContextCoordinates,
    ) -> str | None:
        """返回同一 physical document 中紧邻 seed 的下一 unit；末 unit 返回 ``None``。

        ★ procedure continuation 只能向后补正文，不能把前一片伪装成“缺失后续”。这里仍只
        返回 opaque identity；调用方必须先做 ACL，再通过 ``__call__`` 校验正文和坐标。
        """

        try:
            with self._connection_lock:
                rows = self._connection.execute(
                    """
                    SELECT unit_identity, normalized_start, normalized_end
                    FROM units
                    WHERE physical_source_identity = ?
                    ORDER BY normalized_start ASC, normalized_end ASC, unit_identity ASC
                    """,
                    (coordinates.physical_source_identity,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise RetrievalAdapterError("retrieval_context_unavailable", str(exc)) from exc
        identities = [str(row["unit_identity"]) for row in rows]
        try:
            index = identities.index(coordinates.unit_identity)
        except ValueError as exc:
            raise RetrievalAdapterError(
                "retrieval_context_invalid", "seed unit 不属于当前 physical document"
            ) from exc
        return identities[index + 1] if index + 1 < len(identities) else None


class EnterpriseProfileRuntime:
    """封装同一只读连接上的 bundle、adapter、context loader 和现有回答链路。"""

    def __init__(
        self,
        *,
        connection: sqlite3.Connection,
        selection: EnterpriseProfileSelection,
        manifest: ExternalProfileManifest,
    ) -> None:
        self._connection = connection
        self.selection = selection
        self.manifest = manifest
        self.bundle = _load_bundle(connection, manifest)
        # lifespan runtime 会被多个请求线程共享；正文和 lexical 查询共用同一只读连接锁。
        self._connection_lock = RLock()
        self.adapter = EnterpriseSqliteRetrievalAdapter(
            connection, connection_lock=self._connection_lock
        )
        self.context_loader = EnterpriseContextLoader(
            connection, connection_lock=self._connection_lock
        )
        self._closed = False

    def active_loader(self) -> tuple[EnterpriseProfileSelection, EnterpriseProfileBundle]:
        """沿用旧 active-loader seam；显式 candidate 也保留其 lifecycle 事实。"""

        return self.selection, self.bundle

    def knowledge_tool(self) -> KnowledgeTool:
        return KnowledgeTool(
            adapter=self.adapter,
            active_loader=self.active_loader,
            context_loader=self.context_loader,
        )

    def answer_flow(self) -> RAGAnswerFlow:
        return RAGAnswerFlow(
            knowledge_tool=self.knowledge_tool(),
            active_loader=self.active_loader,
        )

    def close(self) -> None:
        """幂等释放 adapter 与 SQLite；初始化失败/应用 shutdown 可安全共用。"""

        if self._closed:
            return
        adapter_close = getattr(self.adapter, "close", None)
        if callable(adapter_close):
            adapter_close()
        self._connection.close()
        self._closed = True

    def __enter__(self) -> "EnterpriseProfileRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def load_enterprise_profile_runtime(
    *, root: Path, profile_identity: str | None = None, allow_cross_thread: bool = False
) -> EnterpriseProfileRuntime:
    """显式 identity 可验证 candidate；跨线程开关不改变只读与 identity 校验。"""

    pointer: ExternalProfilePointer | None
    if profile_identity is None:
        pointer, manifest = load_active_external_profile(root=root)
        selection = EnterpriseProfileSelection(
            profile_identity=manifest.profile_identity,
            lifecycle_status="active",
            pointer_identity=pointer.pointer_identity,
        )
    else:
        manifest = verify_external_profile(root=root, profile_identity=profile_identity)
        selection = EnterpriseProfileSelection(
            profile_identity=manifest.profile_identity,
            lifecycle_status="candidate",
        )
    database_path = root / manifest.profile_identity / manifest.database_file
    connection = _open_read_only(database_path, allow_cross_thread=allow_cross_thread)
    try:
        return EnterpriseProfileRuntime(
            connection=connection,
            selection=selection,
            manifest=manifest,
        )
    except Exception:
        connection.close()
        raise
