"""EnterpriseRAG 独立 external profile 的不可变构建、校验与 active pointer。

旧 ``ReleaseBundle`` 为 22 条短知识设计，会把全文内嵌进单个 JSON。M34 的 3.6 万文档/
13.9 万 units 使用项目外 SQLite 投影：document catalog、受控 context 与 FTS 索引在同一
immutable database identity 下构建；完整校验后才能切 benchmark 专属 pointer。业务 Knowledge
release 和 pointer 从不在本模块的路径范围内。
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping
from uuid import uuid4

from engine.governance import DOCUMENT_AUTHORIZATION_POLICY_IDENTITY, OUTBOUND_POLICY_IDENTITY
from engine.rag.enterprise_dataset import DatasetAudit, canonical_identity
from engine.rag.enterprise_parser import (
    DEFAULT_PARSER_RECIPE,
    NormalizedDocument,
    ParserRecipe,
    iter_normalized_documents,
)
from engine.rag.enterprise_units import PARAGRAPH_2400_RECIPE, UnitRecipe, build_retrieval_units


PROFILE_FORMAT = "enterprise-knowledge-profile-v1"
POINTER_FORMAT = "enterprise-knowledge-active-pointer-v1"
LEXICAL_INDEX_IDENTITY = "knowledge-sqlite-fts5-unicode61-v1"
PROFILE_DATABASE_NAME = "knowledge.sqlite3"
PROFILE_MANIFEST_NAME = "profile.json"
ACTIVE_POINTER_NAME = "active.json"


class ExternalProfileError(RuntimeError):
    """external profile 的失败关闭异常。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class ExternalProfileManifest:
    """一个完整、可重载 candidate profile 的长期身份。"""

    format: str
    lifecycle_status: str
    profile_identity: str
    dataset_identity: str
    corpus_identity: str
    question_set_identity: str
    parser_identity: str
    parser_recipe_version: str
    unit_recipe_identity: str
    unit_recipe_version: str
    index_identity: str
    authorization_policy_identity: str
    outbound_policy_identity: str
    document_count: int
    unit_count: int
    database_file: str
    database_sha256: str
    database_bytes: int
    build_seconds: float
    manifest_identity: str

    def unsigned_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("manifest_identity")
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_payload(), "manifest_identity": self.manifest_identity}


@dataclass(frozen=True)
class ExternalProfilePointer:
    """benchmark profile 独立 pointer；previous 支持显式回滚。"""

    format: str
    active_profile_identity: str
    previous_profile_identity: str | None
    pointer_identity: str

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "active_profile_identity": self.active_profile_identity,
            "previous_profile_identity": self.previous_profile_identity,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_payload(), "pointer_identity": self.pointer_identity}


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """同目录临时文件 + os.replace，避免 pointer/manifest 半写。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _profile_identity(
    audit: DatasetAudit, parser_recipe: ParserRecipe, unit_recipe: UnitRecipe
) -> str:
    return canonical_identity(
        {
            "format": PROFILE_FORMAT,
            "dataset_identity": audit.dataset_identity,
            "corpus_identity": audit.corpus_identity,
            "parser_identity": parser_recipe.identity,
            "unit_recipe_identity": unit_recipe.identity,
            "index_identity": LEXICAL_INDEX_IDENTITY,
            "authorization_policy_identity": DOCUMENT_AUTHORIZATION_POLICY_IDENTITY,
            "outbound_policy_identity": OUTBOUND_POLICY_IDENTITY,
        }
    )


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=MEMORY;

        CREATE TABLE profile_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE documents (
            physical_source_identity TEXT PRIMARY KEY,
            logical_document_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            document_revision TEXT NOT NULL,
            normalized_content_sha256 TEXT NOT NULL
        );
        CREATE INDEX documents_logical_id_idx ON documents(logical_document_id);
        CREATE INDEX documents_source_type_idx ON documents(source_type);

        CREATE TABLE units (
            row_id INTEGER PRIMARY KEY,
            unit_identity TEXT NOT NULL UNIQUE,
            physical_source_identity TEXT NOT NULL,
            logical_document_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            document_revision TEXT NOT NULL,
            normalized_start INTEGER NOT NULL,
            normalized_end INTEGER NOT NULL,
            anchor TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY(physical_source_identity) REFERENCES documents(physical_source_identity)
        );
        CREATE INDEX units_physical_source_idx ON units(physical_source_identity);
        CREATE INDEX units_logical_document_idx ON units(logical_document_id);
        CREATE VIRTUAL TABLE units_fts USING fts5(
            content,
            content='',
            tokenize='unicode61'
        );
        """
    )


def _insert_documents_and_units(
    connection: sqlite3.Connection,
    documents: Iterable[NormalizedDocument],
    unit_recipe: UnitRecipe,
) -> tuple[int, int]:
    document_count = 0
    unit_count = 0
    document_batch: list[tuple[Any, ...]] = []
    unit_batch: list[tuple[Any, ...]] = []
    fts_batch: list[tuple[Any, ...]] = []

    def flush() -> None:
        if document_batch:
            connection.executemany(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)", document_batch
            )
            document_batch.clear()
        if unit_batch:
            connection.executemany(
                "INSERT INTO units VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                unit_batch,
            )
            connection.executemany(
                "INSERT INTO units_fts(rowid, content) VALUES (?, ?)", fts_batch
            )
            unit_batch.clear()
            fts_batch.clear()

    for document in documents:
        source = document.source_instance
        document_count += 1
        document_batch.append(
            (
                source.physical_identity,
                source.logical_document_id,
                source.source_type,
                source.relative_path,
                document.title,
                document.document_revision,
                document.content_sha256,
            )
        )
        for unit in build_retrieval_units(document, unit_recipe):
            unit_count += 1
            unit_batch.append(
                (
                    unit_count,
                    unit.unit_identity,
                    unit.physical_source_identity,
                    unit.logical_document_id,
                    unit.source_type,
                    document.title,
                    unit.document_revision,
                    unit.normalized_start,
                    unit.normalized_end,
                    unit.anchor,
                    unit.content_sha256,
                    unit.content,
                )
            )
            fts_batch.append((unit_count, unit.content))
        if len(unit_batch) >= 1000:
            flush()
    flush()
    return document_count, unit_count


def build_candidate_external_profile(
    *,
    root: Path,
    audit: DatasetAudit,
    parser_recipe: ParserRecipe = DEFAULT_PARSER_RECIPE,
    unit_recipe: UnitRecipe = PARAGRAPH_2400_RECIPE,
) -> ExternalProfileManifest:
    """构建 immutable candidate；已有同 identity 时只验证复用，不追加写入。"""

    identity = _profile_identity(audit, parser_recipe, unit_recipe)
    target = root / identity
    if target.exists():
        return verify_external_profile(root=root, profile_identity=identity)

    root.mkdir(parents=True, exist_ok=True)
    building = root / f".building-{identity[:16]}-{uuid4().hex}"
    building.mkdir()
    database_path = building / PROFILE_DATABASE_NAME
    started = perf_counter()
    connection = sqlite3.connect(database_path)
    try:
        _create_schema(connection)
        document_count, unit_count = _insert_documents_and_units(
            connection, iter_normalized_documents(audit, parser_recipe), unit_recipe
        )
        meta = {
            "format": PROFILE_FORMAT,
            "profile_identity": identity,
            "dataset_identity": audit.dataset_identity,
            "corpus_identity": audit.corpus_identity,
            "question_set_identity": audit.question_set_identity,
            "parser_identity": parser_recipe.identity,
            "unit_recipe_identity": unit_recipe.identity,
            "index_identity": LEXICAL_INDEX_IDENTITY,
            "document_count": str(document_count),
            "unit_count": str(unit_count),
        }
        connection.executemany(
            "INSERT INTO profile_meta(key, value) VALUES (?, ?)", sorted(meta.items())
        )
        connection.commit()
    except Exception:
        connection.close()
        raise
    connection.close()

    unsigned = {
        "format": PROFILE_FORMAT,
        "lifecycle_status": "candidate",
        "profile_identity": identity,
        "dataset_identity": audit.dataset_identity,
        "corpus_identity": audit.corpus_identity,
        "question_set_identity": audit.question_set_identity,
        "parser_identity": parser_recipe.identity,
        "parser_recipe_version": parser_recipe.recipe_version,
        "unit_recipe_identity": unit_recipe.identity,
        "unit_recipe_version": unit_recipe.recipe_version,
        "index_identity": LEXICAL_INDEX_IDENTITY,
        "authorization_policy_identity": DOCUMENT_AUTHORIZATION_POLICY_IDENTITY,
        "outbound_policy_identity": OUTBOUND_POLICY_IDENTITY,
        "document_count": document_count,
        "unit_count": unit_count,
        "database_file": PROFILE_DATABASE_NAME,
        "database_sha256": _file_sha256(database_path),
        "database_bytes": database_path.stat().st_size,
        "build_seconds": round(perf_counter() - started, 6),
    }
    manifest = ExternalProfileManifest(
        **unsigned,
        manifest_identity=canonical_identity(unsigned),
    )
    _atomic_write_json(building / PROFILE_MANIFEST_NAME, manifest.to_dict())
    _verify_profile_directory(building, expected_identity=identity)
    try:
        os.replace(building, target)
    except OSError as exc:
        raise ExternalProfileError("profile_publish_failed", str(exc)) from exc
    return verify_external_profile(root=root, profile_identity=identity)


def _manifest_from_path(path: Path) -> ExternalProfileManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ExternalProfileManifest(**payload)
    except FileNotFoundError as exc:
        raise ExternalProfileError("profile_not_found", str(path)) from exc
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ExternalProfileError("profile_manifest_invalid", str(exc)) from exc


def _verify_profile_directory(
    directory: Path, *, expected_identity: str | None = None
) -> ExternalProfileManifest:
    manifest = _manifest_from_path(directory / PROFILE_MANIFEST_NAME)
    if manifest.format != PROFILE_FORMAT or manifest.lifecycle_status != "candidate":
        raise ExternalProfileError("profile_manifest_invalid", "format/lifecycle")
    if expected_identity and manifest.profile_identity != expected_identity:
        raise ExternalProfileError("profile_identity_mismatch", "directory/manifest")
    if canonical_identity(manifest.unsigned_payload()) != manifest.manifest_identity:
        raise ExternalProfileError("profile_manifest_hash_mismatch", manifest.profile_identity)
    if manifest.database_file != PROFILE_DATABASE_NAME:
        raise ExternalProfileError("profile_manifest_invalid", "database_file")
    database_path = directory / manifest.database_file
    if not database_path.is_file():
        raise ExternalProfileError("profile_database_missing", str(database_path))
    if database_path.stat().st_size != manifest.database_bytes:
        raise ExternalProfileError("profile_database_size_mismatch", manifest.profile_identity)
    if _file_sha256(database_path) != manifest.database_sha256:
        raise ExternalProfileError("profile_database_hash_mismatch", manifest.profile_identity)

    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        unit_count = connection.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        fts_count = connection.execute("SELECT COUNT(*) FROM units_fts").fetchone()[0]
        meta = dict(connection.execute("SELECT key, value FROM profile_meta").fetchall())
    except sqlite3.Error as exc:
        raise ExternalProfileError("profile_database_invalid", str(exc)) from exc
    finally:
        connection.close()
    if integrity != "ok":
        raise ExternalProfileError("profile_database_invalid", str(integrity))
    if (
        document_count != manifest.document_count
        or unit_count != manifest.unit_count
        or fts_count != manifest.unit_count
    ):
        raise ExternalProfileError("profile_row_count_mismatch", manifest.profile_identity)
    expected_meta = {
        "format": manifest.format,
        "profile_identity": manifest.profile_identity,
        "dataset_identity": manifest.dataset_identity,
        "corpus_identity": manifest.corpus_identity,
        "question_set_identity": manifest.question_set_identity,
        "parser_identity": manifest.parser_identity,
        "unit_recipe_identity": manifest.unit_recipe_identity,
        "index_identity": manifest.index_identity,
        "document_count": str(manifest.document_count),
        "unit_count": str(manifest.unit_count),
    }
    if meta != expected_meta:
        raise ExternalProfileError("profile_database_identity_mismatch", manifest.profile_identity)
    return manifest


def verify_external_profile(
    *, root: Path, profile_identity: str
) -> ExternalProfileManifest:
    """只读重载并完整校验 candidate。"""

    if not profile_identity.strip():
        raise ExternalProfileError("profile_identity_missing", "profile_identity")
    return _verify_profile_directory(
        root / profile_identity, expected_identity=profile_identity
    )


def _load_pointer(path: Path) -> ExternalProfilePointer:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pointer = ExternalProfilePointer(**payload)
    except FileNotFoundError as exc:
        raise ExternalProfileError("active_profile_unavailable", str(path)) from exc
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ExternalProfileError("active_pointer_invalid", str(exc)) from exc
    if pointer.format != POINTER_FORMAT:
        raise ExternalProfileError("active_pointer_invalid", "format")
    if canonical_identity(pointer.unsigned_payload()) != pointer.pointer_identity:
        raise ExternalProfileError("active_pointer_hash_mismatch", "pointer")
    return pointer


def activate_external_profile(
    *, root: Path, profile_identity: str
) -> tuple[ExternalProfilePointer, ExternalProfileManifest]:
    """candidate 完整验证后，原子切换 benchmark 专属 pointer。"""

    manifest = verify_external_profile(root=root, profile_identity=profile_identity)
    pointer_path = root / ACTIVE_POINTER_NAME
    previous: str | None = None
    if pointer_path.exists():
        previous = _load_pointer(pointer_path).active_profile_identity
    unsigned = {
        "format": POINTER_FORMAT,
        "active_profile_identity": profile_identity,
        "previous_profile_identity": previous if previous != profile_identity else None,
    }
    pointer = ExternalProfilePointer(
        **unsigned, pointer_identity=canonical_identity(unsigned)
    )
    _atomic_write_json(pointer_path, pointer.to_dict())
    loaded_pointer, loaded_manifest = load_active_external_profile(root=root)
    if loaded_pointer != pointer or loaded_manifest.profile_identity != profile_identity:
        raise ExternalProfileError("active_pointer_switch_failed", profile_identity)
    return loaded_pointer, loaded_manifest


def load_active_external_profile(
    *, root: Path
) -> tuple[ExternalProfilePointer, ExternalProfileManifest]:
    pointer = _load_pointer(root / ACTIVE_POINTER_NAME)
    manifest = verify_external_profile(
        root=root, profile_identity=pointer.active_profile_identity
    )
    return pointer, manifest


def inspect_external_profile_state(*, root: Path) -> dict[str, Any]:
    """不读取正文的轻量 inspect；pointer 不可用时如实报告。"""

    profiles = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".building-")
    ) if root.is_dir() else []
    try:
        pointer, manifest = load_active_external_profile(root=root)
    except ExternalProfileError as exc:
        return {
            "active": False,
            "reason_code": exc.reason_code,
            "profile_count": len(profiles),
            "profile_identities": profiles,
        }
    return {
        "active": True,
        "active_profile_identity": pointer.active_profile_identity,
        "previous_profile_identity": pointer.previous_profile_identity,
        "profile_count": len(profiles),
        "profile_identities": profiles,
        "document_count": manifest.document_count,
        "unit_count": manifest.unit_count,
        "index_identity": manifest.index_identity,
    }
