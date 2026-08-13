"""不可变 Knowledge release bundle 与原子 active pointer。

authority source 仍由 M30 catalog builder 管理。本模块只把完整 staged 快照固化为可重载投影，
并坚持“先写新 bundle、完整复算、最后切 pointer”。任何校验失败都不会尝试猜一个旧版本自动
复活；显式 rollback 也必须重新对照当前 authority 和 policy。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from engine.governance import DOCUMENT_AUTHORIZATION_POLICY_IDENTITY, OUTBOUND_POLICY_IDENTITY
from engine.rag.catalog import CatalogEntry, StagedCatalog

RELEASE_FORMAT = "knowledge-release-v1"
ACTIVE_POINTER_FORMAT = "knowledge-active-pointer-v1"
PHASE4_CONTRACT_VERSION = "phase4-v1"
DEFAULT_RELEASE_ROOT = Path(__file__).resolve().parents[2] / "domain_pack" / "kb_releases"


class ReleaseError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _canonical_bytes(payload: Mapping[str, Any] | list[Any]) -> bytes:
    """生成无 key 顺序和空白噪声的规范 JSON bytes。"""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(payload: Mapping[str, Any] | list[Any]) -> str:
    """计算 release/pointer 共用的 canonical SHA-256。"""

    return sha256(_canonical_bytes(payload)).hexdigest()


def _entry_record(entry: CatalogEntry, *, include_content: bool) -> dict[str, Any]:
    """在完整 bundle 与安全 manifest 之间复用同一 entry 投影。"""

    record = entry.manifest_record()
    if include_content:
        record["content"] = entry.content
    return record


def _entry_from_record(record: Mapping[str, Any]) -> CatalogEntry:
    """closed-world 重建 entry，并复算正文语义 identity。"""

    expected = {
        "document_key", "revision", "authority_ref", "source_kind", "source_key", "title",
        "knowledge_type", "status", "anchor", "data_class", "purposes", "public", "allowed_roles",
        "content_identity", "usable", "content",
    }
    if set(record) != expected:
        raise ReleaseError("release_closed_world_invalid", "release entry 字段不完整或包含未知字段")
    entry = CatalogEntry(
        document_key=str(record["document_key"]),
        revision=str(record["revision"]),
        authority_ref=str(record["authority_ref"]),
        source_kind=str(record["source_kind"]),
        source_key=str(record["source_key"]),
        title=str(record["title"]),
        knowledge_type=str(record["knowledge_type"]),
        status=str(record["status"]),
        anchor=str(record["anchor"]),
        data_class=str(record["data_class"]),
        purposes=tuple(str(value) for value in record["purposes"]),
        public=bool(record["public"]),
        allowed_roles=frozenset(str(value) for value in record["allowed_roles"]),
        content=str(record["content"]),
        content_identity=str(record["content_identity"]),
    )
    if bool(record["usable"]) != entry.is_usable:
        raise ReleaseError("release_closed_world_invalid", "usable 与 status 不一致")
    semantic = {
        "title": entry.title,
        "knowledge_type": entry.knowledge_type,
        "status": entry.status,
        "data_class": entry.data_class,
        "purposes": list(entry.purposes),
        "public": entry.public,
        "allowed_roles": sorted(entry.allowed_roles),
        "content": entry.content,
    }
    if _hash(semantic) != entry.content_identity:
        raise ReleaseError("release_content_hash_mismatch", "entry content identity 校验失败")
    return entry


@dataclass(frozen=True)
class ReleaseBundle:
    """可独立重载的完整不可变 Knowledge corpus 投影。"""

    release_identity: str
    corpus_identity: str
    source_build_identity: str
    recipe_identity: str
    authorization_policy_identity: str
    outbound_policy_identity: str
    contract_version: str
    entries: tuple[CatalogEntry, ...]

    def unsigned_payload(self) -> dict[str, Any]:
        """返回参与 release identity 的完整规范 payload。"""

        return {
            "format": RELEASE_FORMAT,
            "corpus_identity": self.corpus_identity,
            "source_build_identity": self.source_build_identity,
            "recipe_identity": self.recipe_identity,
            "authorization_policy_identity": self.authorization_policy_identity,
            "outbound_policy_identity": self.outbound_policy_identity,
            "contract_version": self.contract_version,
            "entries": [_entry_record(entry, include_content=True) for entry in self.entries],
        }

    def to_dict(self) -> dict[str, Any]:
        """附加 release identity，形成落盘结构。"""

        return {**self.unsigned_payload(), "release_identity": self.release_identity}

    def safe_manifest(self) -> dict[str, Any]:
        return {
            "format": RELEASE_FORMAT,
            "release_identity": self.release_identity,
            "corpus_identity": self.corpus_identity,
            "source_build_identity": self.source_build_identity,
            "entry_count": len(self.entries),
            "authorization_policy_identity": self.authorization_policy_identity,
            "outbound_policy_identity": self.outbound_policy_identity,
            "contract_version": self.contract_version,
            "entries": [_entry_record(entry, include_content=False) for entry in self.entries],
        }


@dataclass(frozen=True)
class G3Approval:
    """与 bundle 分离的用户正式发布决定。"""

    decision: str
    approved_by_ref: str
    approved_at: str

    def __post_init__(self) -> None:
        """只接受用户已确认的 G3 方案 A 记录。"""

        if self.decision != "A" or not self.approved_by_ref.strip() or not self.approved_at.strip():
            raise ReleaseError("g3_approval_invalid", "激活只接受完整的 G3 方案 A approval record")


@dataclass(frozen=True)
class ActivePointer:
    """当前/上一 release 与 policy/contract 的原子切换事实。"""

    current_release_identity: str
    previous_release_identity: str | None
    authorization_policy_identity: str
    outbound_policy_identity: str
    contract_version: str
    approval: G3Approval
    pointer_identity: str

    def unsigned_payload(self) -> dict[str, Any]:
        """返回参与 pointer identity 的 current/previous/policy 事实。"""

        return {
            "format": ACTIVE_POINTER_FORMAT,
            "current_release_identity": self.current_release_identity,
            "previous_release_identity": self.previous_release_identity,
            "authorization_policy_identity": self.authorization_policy_identity,
            "outbound_policy_identity": self.outbound_policy_identity,
            "contract_version": self.contract_version,
            "approval": asdict(self.approval),
        }

    def to_dict(self) -> dict[str, Any]:
        """附加 pointer identity，形成落盘结构。"""

        return {**self.unsigned_payload(), "pointer_identity": self.pointer_identity}


def _release_path(root: Path, release_identity: str) -> Path:
    """把 release identity 映射到唯一 immutable bundle 路径。"""

    return root / "releases" / f"{release_identity}.json"


def _pointer_path(root: Path) -> Path:
    """返回该 release root 唯一 active pointer 路径。"""

    return root / "active.json"


def _restore_pointer_after_failed_switch(root: Path, old: ActivePointer | None) -> None:
    """仅恢复本次精确 pointer；不会删除 bundle、authority 或任何宽目录。"""

    path = _pointer_path(root)
    if old is None:
        path.unlink(missing_ok=True)
    else:
        _atomic_write(path, old.to_dict())


def _atomic_write(path: Path, payload: Mapping[str, Any], *, replace: Callable[[Path, Path], None] | None = None) -> None:
    """同目录临时文件 + replace；故障注入可以证明 pointer 失败不会改旧 active。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(_canonical_bytes(payload) + b"\n")
        if replace is None:
            temporary.replace(path)
        else:
            replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _catalog_manifest_identity(entries: tuple[CatalogEntry, ...]) -> str:
    """按 M30 的无正文 manifest 规则复算 corpus identity。"""

    return _hash({"entries": [_entry_record(entry, include_content=False) for entry in entries]})


def build_candidate_release(
    *,
    staged: StagedCatalog,
    root: Path = DEFAULT_RELEASE_ROOT,
    recipe_identity: str = "knowledge-release-recipe-v1",
    authorization_policy_identity: str = DOCUMENT_AUTHORIZATION_POLICY_IDENTITY,
    outbound_policy_identity: str = OUTBOUND_POLICY_IDENTITY,
    contract_version: str = PHASE4_CONTRACT_VERSION,
) -> ReleaseBundle:
    """固化完整 candidate；相同 identity 已存在时只接受逐字节相同的 immutable 文件。"""

    entries = staged.usable_entries
    if not entries or len(entries) != len(staged.entries):
        raise ReleaseError("release_catalog_not_fully_usable", "M31 首版只发布全量 active staged catalog")
    if _catalog_manifest_identity(entries) != staged.corpus_identity:
        raise ReleaseError("release_corpus_identity_mismatch", "staged corpus identity 无法复算")
    unsigned = {
        "format": RELEASE_FORMAT,
        "corpus_identity": staged.corpus_identity,
        "source_build_identity": staged.build_identity,
        "recipe_identity": recipe_identity,
        "authorization_policy_identity": authorization_policy_identity,
        "outbound_policy_identity": outbound_policy_identity,
        "contract_version": contract_version,
        "entries": [_entry_record(entry, include_content=True) for entry in entries],
    }
    bundle = ReleaseBundle(
        release_identity=_hash(unsigned),
        corpus_identity=staged.corpus_identity,
        source_build_identity=staged.build_identity,
        recipe_identity=recipe_identity,
        authorization_policy_identity=authorization_policy_identity,
        outbound_policy_identity=outbound_policy_identity,
        contract_version=contract_version,
        entries=entries,
    )
    path = _release_path(root, bundle.release_identity)
    if path.exists():
        existing = path.read_bytes().rstrip(b"\r\n")
        if existing != _canonical_bytes(bundle.to_dict()):
            raise ReleaseError("release_immutable_conflict", "相同 release identity 的文件内容不同")
    else:
        _atomic_write(path, bundle.to_dict())
    reloaded = load_release(root=root, release_identity=bundle.release_identity)
    if reloaded != bundle:
        raise ReleaseError("release_reload_mismatch", "candidate 写入后重载不一致")
    return bundle


def load_release(*, root: Path = DEFAULT_RELEASE_ROOT, release_identity: str) -> ReleaseBundle:
    """closed-world 读取并复算校验 bundle：字段集合、format、identity、entry content hash 与
    corpus identity 全部对账，任一失败都返回有限 reason code 的 ReleaseError，绝不返回半成品。"""

    path = _release_path(root, release_identity)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("release_unavailable", "release bundle 无法读取") from exc
    expected = {
        "format", "release_identity", "corpus_identity", "source_build_identity", "recipe_identity",
        "authorization_policy_identity", "outbound_policy_identity", "contract_version", "entries",
    }
    if not isinstance(raw, dict) or set(raw) != expected or raw.get("format") != RELEASE_FORMAT:
        raise ReleaseError("release_closed_world_invalid", "release 顶层字段或 format 非法")
    if raw["release_identity"] != release_identity:
        raise ReleaseError("release_identity_mismatch", "文件名、pointer 与 bundle identity 不一致")
    if not isinstance(raw["entries"], list):
        raise ReleaseError("release_closed_world_invalid", "entries 必须是列表")
    entries = tuple(_entry_from_record(record) for record in raw["entries"] if isinstance(record, dict))
    if len(entries) != len(raw["entries"]):
        raise ReleaseError("release_closed_world_invalid", "entry 必须是对象")
    bundle = ReleaseBundle(
        release_identity=str(raw["release_identity"]),
        corpus_identity=str(raw["corpus_identity"]),
        source_build_identity=str(raw["source_build_identity"]),
        recipe_identity=str(raw["recipe_identity"]),
        authorization_policy_identity=str(raw["authorization_policy_identity"]),
        outbound_policy_identity=str(raw["outbound_policy_identity"]),
        contract_version=str(raw["contract_version"]),
        entries=entries,
    )
    if _hash(bundle.unsigned_payload()) != bundle.release_identity:
        raise ReleaseError("release_hash_mismatch", "bundle canonical hash 校验失败")
    if _catalog_manifest_identity(entries) != bundle.corpus_identity:
        raise ReleaseError("release_corpus_identity_mismatch", "bundle corpus identity 校验失败")
    return bundle


def validate_release_against_staged(bundle: ReleaseBundle, staged: StagedCatalog) -> None:
    """证明 release 仍与当前 authority 构建结果逐项一致。"""

    if (
        bundle.corpus_identity != staged.corpus_identity
        or bundle.source_build_identity != staged.build_identity
        or bundle.entries != staged.usable_entries
    ):
        raise ReleaseError("release_authority_mismatch", "release 与当前 staged authority 不一致")


def _load_pointer(root: Path) -> ActivePointer:
    """closed-world 读取并复算 active pointer。"""

    try:
        raw = json.loads(_pointer_path(root).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError("active_pointer_unavailable", "active pointer 无法读取") from exc
    expected = {
        "format", "current_release_identity", "previous_release_identity", "authorization_policy_identity",
        "outbound_policy_identity", "contract_version", "approval", "pointer_identity",
    }
    if not isinstance(raw, dict) or set(raw) != expected or raw.get("format") != ACTIVE_POINTER_FORMAT:
        raise ReleaseError("active_pointer_invalid", "active pointer 字段或 format 非法")
    if not isinstance(raw["approval"], dict):
        raise ReleaseError("active_pointer_invalid", "approval 非法")
    try:
        approval = G3Approval(**raw["approval"])
    except (TypeError, ReleaseError) as exc:
        raise ReleaseError("active_pointer_invalid", "approval 非法") from exc
    pointer = ActivePointer(
        current_release_identity=str(raw["current_release_identity"]),
        previous_release_identity=(str(raw["previous_release_identity"]) if raw["previous_release_identity"] else None),
        authorization_policy_identity=str(raw["authorization_policy_identity"]),
        outbound_policy_identity=str(raw["outbound_policy_identity"]),
        contract_version=str(raw["contract_version"]),
        approval=approval,
        pointer_identity=str(raw["pointer_identity"]),
    )
    if _hash(pointer.unsigned_payload()) != pointer.pointer_identity:
        raise ReleaseError("active_pointer_hash_mismatch", "active pointer hash 校验失败")
    return pointer


def activate_release(
    *,
    bundle: ReleaseBundle,
    staged: StagedCatalog,
    approval: G3Approval,
    root: Path = DEFAULT_RELEASE_ROOT,
    replace: Callable[[Path, Path], None] | None = None,
) -> ActivePointer:
    """验证 candidate 后原子推进 active；replace 只用于确定性 fault injection。"""

    reloaded = load_release(root=root, release_identity=bundle.release_identity)
    validate_release_against_staged(reloaded, staged)
    pointer_path = _pointer_path(root)
    old = _load_pointer(root) if pointer_path.exists() else None
    if old is not None and old.current_release_identity == bundle.release_identity:
        return old
    pointer = ActivePointer(
        current_release_identity=bundle.release_identity,
        previous_release_identity=old.current_release_identity if old else None,
        authorization_policy_identity=bundle.authorization_policy_identity,
        outbound_policy_identity=bundle.outbound_policy_identity,
        contract_version=bundle.contract_version,
        approval=approval,
        pointer_identity="",
    )
    pointer = ActivePointer(**{**pointer.__dict__, "pointer_identity": _hash(pointer.unsigned_payload())})
    try:
        _atomic_write(pointer_path, pointer.to_dict(), replace=replace)
        loaded_pointer, loaded_bundle = load_active_release(root=root)
        if loaded_pointer != pointer or loaded_bundle != bundle:
            raise ReleaseError("active_reload_mismatch", "active 切换后重载不一致")
    except Exception as switch_failure:
        try:
            _restore_pointer_after_failed_switch(root, old)
        except Exception as restore_failure:
            raise ReleaseError("active_restore_failed", "切换失败且旧 pointer 恢复失败") from restore_failure
        raise switch_failure
    return pointer


def load_active_release(*, root: Path = DEFAULT_RELEASE_ROOT) -> tuple[ActivePointer, ReleaseBundle]:
    """启动恢复入口；active 损坏时失败关闭，不自动选择 previous。"""

    pointer = _load_pointer(root)
    bundle = load_release(root=root, release_identity=pointer.current_release_identity)
    if (
        pointer.authorization_policy_identity != bundle.authorization_policy_identity
        or pointer.outbound_policy_identity != bundle.outbound_policy_identity
        or pointer.contract_version != bundle.contract_version
    ):
        raise ReleaseError("active_policy_mismatch", "pointer 与 release policy/contract 不一致")
    return pointer, bundle


def rollback_active_release(
    *,
    current_authority: StagedCatalog,
    approval: G3Approval,
    root: Path = DEFAULT_RELEASE_ROOT,
) -> ActivePointer:
    """显式回滚；旧 bundle 必须仍是当前 authority 的完整 active revision 集。"""

    pointer, _ = load_active_release(root=root)
    if not pointer.previous_release_identity:
        raise ReleaseError("rollback_previous_missing", "没有可回滚 previous release")
    previous = load_release(root=root, release_identity=pointer.previous_release_identity)
    validate_release_against_staged(previous, current_authority)
    if (
        previous.authorization_policy_identity != DOCUMENT_AUTHORIZATION_POLICY_IDENTITY
        or previous.outbound_policy_identity != OUTBOUND_POLICY_IDENTITY
        or previous.contract_version != PHASE4_CONTRACT_VERSION
    ):
        raise ReleaseError("rollback_policy_mismatch", "previous release 的当前 policy/contract 已失效")
    restored = ActivePointer(
        current_release_identity=previous.release_identity,
        previous_release_identity=pointer.current_release_identity,
        authorization_policy_identity=previous.authorization_policy_identity,
        outbound_policy_identity=previous.outbound_policy_identity,
        contract_version=previous.contract_version,
        approval=approval,
        pointer_identity="",
    )
    restored = ActivePointer(**{**restored.__dict__, "pointer_identity": _hash(restored.unsigned_payload())})
    try:
        _atomic_write(_pointer_path(root), restored.to_dict())
        load_active_release(root=root)
    except Exception as switch_failure:
        try:
            _restore_pointer_after_failed_switch(root, pointer)
        except Exception as restore_failure:
            raise ReleaseError("active_restore_failed", "回滚切换失败且原 pointer 恢复失败") from restore_failure
        raise switch_failure
    return restored


def inspect_release_state(*, root: Path = DEFAULT_RELEASE_ROOT) -> dict[str, Any]:
    """安全只读投影；没有 active 时如实返回，而不是把最新 candidate 当 active。"""

    release_ids = sorted(path.stem for path in (root / "releases").glob("*.json")) if (root / "releases").exists() else []
    if not _pointer_path(root).exists():
        return {"active": False, "current": None, "previous": None, "candidate_release_ids": release_ids}
    pointer, bundle = load_active_release(root=root)
    return {
        "active": True,
        "current": pointer.current_release_identity,
        "previous": pointer.previous_release_identity,
        "corpus_identity": bundle.corpus_identity,
        "entry_count": len(bundle.entries),
        "candidate_release_ids": release_ids,
    }


def diff_release_manifests(left: ReleaseBundle, right: ReleaseBundle) -> dict[str, Any]:
    """按 document/revision 对比安全 manifest；不把正文复制进人工审查输出。"""

    def indexed(bundle: ReleaseBundle) -> dict[tuple[str, str], CatalogEntry]:
        """按 document/revision 建立 manifest 对比索引。"""

        return {(entry.document_key, entry.revision): entry for entry in bundle.entries}

    left_entries = indexed(left)
    right_entries = indexed(right)
    left_keys = set(left_entries)
    right_keys = set(right_entries)
    changed = sorted(
        key for key in left_keys & right_keys if left_entries[key].manifest_record() != right_entries[key].manifest_record()
    )
    return {
        "left_release_identity": left.release_identity,
        "right_release_identity": right.release_identity,
        "added": [list(key) for key in sorted(right_keys - left_keys)],
        "removed": [list(key) for key in sorted(left_keys - right_keys)],
        "changed": [list(key) for key in changed],
    }
