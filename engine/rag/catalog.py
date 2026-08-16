"""从可信知识原件确定性构建只读的 staged catalog。

★ Catalog 是一个“深模块”：调用方只交付 authority sources 和可识别的构建配方，
模块内部完成发现、解析、指标派生、完整校验、稳定排序和 identity 计算。成功时返回完整
不可变快照；任何一个条目失败时抛出有限 reason code，不返回看似可用的半成品。

M30 的结果始终是 ``staged``。本文件没有 active pointer、向量索引或生成器接线，避免把
“内容已验证”误写成“内容已经安全发布”。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_SOURCE_DIR = PROJECT_ROOT / "domain_pack" / "kb_docs"
DEFAULT_METRICS_PATH = PROJECT_ROOT / "domain_pack" / "metrics.yaml"
DEFAULT_METRIC_PROJECTIONS_PATH = DEFAULT_POLICY_SOURCE_DIR / "metric_projections.yaml"

KNOWN_ROLES = frozenset({"admin", "ops", "customer_service", "demo_user"})
KNOWN_STATUSES = frozenset({"active", "inactive", "revoked"})
KNOWN_DATA_CLASSES = frozenset(
    {
        "role_restricted_policy_text",
        "security_policy",
        "metric_definition",
        # EnterpriseRAG 是公开合成 benchmark，不等同业务 authority。该枚举只允许它
        # 经过独立 external profile 使用，不会让 domain_pack 自动纳入外部语料。
        "public_benchmark_document",
    }
)
KNOWN_PURPOSES = frozenset({"answer_evidence", "analysis_constraint", "generation_context"})
POLICY_REQUIRED_FIELDS = frozenset(
    {
        "document_key",
        "revision",
        "title",
        "knowledge_type",
        "status",
        "anchor",
        "data_class",
        "purposes",
        "public",
        "allowed_roles",
    }
)
METRIC_REQUIRED_FIELDS = POLICY_REQUIRED_FIELDS | {"metric_key"}


# 对外合同 ============================================================================


class CatalogBuildError(ValueError):
    """Catalog 失败关闭异常；``reason_code`` 可供测试和未来 Tool 做稳定分支。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class CatalogBuildRecipe:
    """影响构建语义的最小配方身份。

    ``expected_corpus_identity`` 用于需要锁定已审查输入的调用场景。它不是 M30 的 active
    发布开关；不提供时只构建并报告 identity，提供且不匹配时整体失败。
    """

    identity: str = "knowledge-catalog-v1"
    expected_corpus_identity: str | None = None


@dataclass(frozen=True)
class CatalogEntry:
    """一个可审计的 document revision；集合使用 tuple/frozenset 保持不可变语义。"""

    document_key: str
    revision: str
    authority_ref: str
    source_kind: str
    source_key: str
    title: str
    knowledge_type: str
    status: str
    anchor: str
    data_class: str
    purposes: tuple[str, ...]
    public: bool
    allowed_roles: frozenset[str]
    content: str
    content_identity: str

    @property
    def is_usable(self) -> bool:
        """只有 active 原件能进入 staged usable set；staged 不等于已发布。"""

        return self.status == "active"

    def manifest_record(self) -> dict[str, Any]:
        """返回稳定、可序列化的审计投影，不泄漏可变内部容器。"""

        return {
            "document_key": self.document_key,
            "revision": self.revision,
            "authority_ref": self.authority_ref,
            "source_kind": self.source_kind,
            "source_key": self.source_key,
            "title": self.title,
            "knowledge_type": self.knowledge_type,
            "status": self.status,
            "anchor": self.anchor,
            "data_class": self.data_class,
            "purposes": list(self.purposes),
            "public": self.public,
            "allowed_roles": sorted(self.allowed_roles),
            "content_identity": self.content_identity,
            "usable": self.is_usable,
        }


@dataclass(frozen=True)
class StagedCatalog:
    """一次完整构建的不可变 staged catalog。"""

    entries: tuple[CatalogEntry, ...]
    corpus_identity: str
    build_identity: str
    lifecycle_status: str = "staged"

    @property
    def usable_entries(self) -> tuple[CatalogEntry, ...]:
        """返回可供后续发布模块审查的候选集合，不代表这些条目已 active 发布。"""

        return tuple(entry for entry in self.entries if entry.is_usable)

    def summary(self) -> Mapping[str, Any]:
        """适合人工检查的薄摘要；MappingProxyType 防止调用方原地篡改。"""

        counts_by_source = {
            source_kind: sum(entry.source_kind == source_kind for entry in self.entries)
            for source_kind in sorted({entry.source_kind for entry in self.entries})
        }
        return MappingProxyType(
            {
                "lifecycle_status": self.lifecycle_status,
                "entry_count": len(self.entries),
                "usable_entry_count": len(self.usable_entries),
                "counts_by_source": MappingProxyType(counts_by_source),
                "corpus_identity": self.corpus_identity,
                "build_identity": self.build_identity,
            }
        )

    def manifest(self) -> dict[str, Any]:
        """生成顺序稳定的 manifest，方便 diff；正文只通过 identity 表达。"""

        return {
            "lifecycle_status": self.lifecycle_status,
            "corpus_identity": self.corpus_identity,
            "build_identity": self.build_identity,
            "entries": [entry.manifest_record() for entry in self.entries],
        }


def _fail(reason_code: str, message: str) -> None:
    """统一抛出机器可判异常，避免内部路径泄漏成不稳定异常类型。"""

    raise CatalogBuildError(reason_code, message)


def _normalized_text(value: str) -> str:
    """统一换行和行尾空格；不吞掉正文内部空行或词语差异。"""

    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n"))


def _canonical_hash(payload: Mapping[str, Any] | list[Any]) -> str:
    """先规范 JSON key/分隔符再哈希，使序列化顺序噪声不影响 identity。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """读取 YAML mapping，并把 IO/编码/YAML 差异收敛成同一个 reason code。"""

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        _fail("source_parse_error", f"无法读取 {path}: {exc}")
    if not isinstance(payload, dict):
        _fail("source_parse_error", f"{path} 顶层必须是 mapping")
    return dict(payload)


def _parse_markdown_source(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _fail("source_parse_error", f"无法读取 {path}: {exc}")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n") or "\n---\n" not in normalized[4:]:
        _fail("source_parse_error", f"{path} 缺少完整 YAML front matter")
    metadata_text, body = normalized[4:].split("\n---\n", 1)
    try:
        metadata = yaml.safe_load(metadata_text)
    except yaml.YAMLError as exc:
        _fail("source_parse_error", f"{path} front matter 非法: {exc}")
    if not isinstance(metadata, dict):
        _fail("source_parse_error", f"{path} front matter 必须是 mapping")
    content = _normalized_text(body)
    if not content:
        _fail("missing_required_field", f"{path} 正文为空")
    return dict(metadata), content


def _validated_metadata(raw: Mapping[str, Any], *, source: str, metric: bool) -> dict[str, Any]:
    """一次完成 closed-world 字段、枚举和 ACL 校验，非法输入不做宽松修复。"""

    required = METRIC_REQUIRED_FIELDS if metric else POLICY_REQUIRED_FIELDS
    unknown = set(raw) - required
    if unknown:
        _fail("unknown_field", f"{source} 包含未知字段 {sorted(unknown)}")
    missing = {field for field in required if field not in raw or raw[field] is None}
    if missing:
        _fail("missing_required_field", f"{source} 缺少字段 {sorted(missing)}")

    metadata = dict(raw)
    for field_name in ("document_key", "revision", "title", "knowledge_type", "status", "anchor", "data_class"):
        if not isinstance(metadata[field_name], (str, int)) or not str(metadata[field_name]).strip():
            _fail("missing_required_field", f"{source}.{field_name} 必须是非空文本")
        metadata[field_name] = str(metadata[field_name]).strip()
    if metric:
        if not isinstance(metadata["metric_key"], str) or not metadata["metric_key"].strip():
            _fail("missing_required_field", f"{source}.metric_key 必须是非空文本")
        metadata["metric_key"] = metadata["metric_key"].strip()

    if metadata["status"] not in KNOWN_STATUSES:
        _fail("invalid_enum", f"{source}.status={metadata['status']} 不受支持")
    if metadata["data_class"] not in KNOWN_DATA_CLASSES:
        _fail("invalid_enum", f"{source}.data_class={metadata['data_class']} 不受支持")
    if not isinstance(metadata["purposes"], list) or not metadata["purposes"]:
        _fail("invalid_enum", f"{source}.purposes 必须是非空列表")
    purposes = tuple(sorted({str(item).strip() for item in metadata["purposes"]}))
    unknown_purposes = set(purposes) - KNOWN_PURPOSES
    if unknown_purposes or len(purposes) != len(metadata["purposes"]):
        _fail("invalid_enum", f"{source}.purposes 非法或重复: {metadata['purposes']}")
    metadata["purposes"] = purposes

    if not isinstance(metadata["public"], bool) or not isinstance(metadata["allowed_roles"], list):
        _fail("invalid_acl", f"{source} 的 public/allowed_roles 类型非法")
    roles = frozenset(str(role).strip() for role in metadata["allowed_roles"])
    if len(roles) != len(metadata["allowed_roles"]) or not roles <= KNOWN_ROLES:
        _fail("invalid_acl", f"{source}.allowed_roles 非法或重复: {metadata['allowed_roles']}")
    if metadata["public"] and roles:
        _fail("invalid_acl", f"{source} 不能同时 public=true 且声明 allowed_roles")
    if not metadata["public"] and not roles:
        _fail("invalid_acl", f"{source} 非公开内容必须声明 allowed_roles")
    metadata["allowed_roles"] = roles
    return metadata


def _entry(
    metadata: Mapping[str, Any],
    *,
    authority_ref: str,
    source_kind: str,
    source_key: str,
    content: str,
) -> CatalogEntry:
    """把已验证 metadata 和正文冻结为一个 revision，并计算语义内容 identity。"""

    # content identity 描述“这段知识在语义上是什么”，不混入文件名、key、revision、anchor
    # 等定位坐标。定位坐标仍进入 corpus manifest；这样既能发现重命名/版本变化，也能单独
    # 拦截“换一个 key 重复塞入相同知识”的 duplicate content。
    semantic_payload = {
        "title": metadata["title"],
        "knowledge_type": metadata["knowledge_type"],
        "status": metadata["status"],
        "data_class": metadata["data_class"],
        "purposes": list(metadata["purposes"]),
        "public": metadata["public"],
        "allowed_roles": sorted(metadata["allowed_roles"]),
        "content": content,
    }
    return CatalogEntry(
        document_key=str(metadata["document_key"]),
        revision=str(metadata["revision"]),
        authority_ref=authority_ref,
        source_kind=source_kind,
        source_key=source_key,
        title=str(metadata["title"]),
        knowledge_type=str(metadata["knowledge_type"]),
        status=str(metadata["status"]),
        anchor=str(metadata["anchor"]),
        data_class=str(metadata["data_class"]),
        purposes=tuple(metadata["purposes"]),
        public=bool(metadata["public"]),
        allowed_roles=frozenset(metadata["allowed_roles"]),
        content=content,
        content_identity=_canonical_hash(semantic_payload),
    )


def _policy_entries(source_dir: Path) -> list[CatalogEntry]:
    """按文件名稳定发现 Markdown authority source。"""

    entries: list[CatalogEntry] = []
    for path in sorted(source_dir.glob("*.md"), key=lambda item: item.name):
        metadata, content = _parse_markdown_source(path)
        validated = _validated_metadata(metadata, source=str(path), metric=False)
        authority_ref = f"domain_pack/kb_docs/{path.name}#{validated['anchor']}"
        entries.append(
            _entry(validated, authority_ref=authority_ref, source_kind="policy_markdown", source_key=path.name, content=content)
        )
    return entries


def _metric_content(metric_key: str, metric: Mapping[str, Any]) -> str:
    """只从 metrics.yaml 生成说明；projection 配置无正文编辑入口。"""

    lines = [
        f"# {metric.get('name', metric_key)}",
        "",
        f"指标键：`{metric_key}`",
        f"公式：`{metric.get('formula', '')}`",
        f"说明：{metric.get('description', '')}",
    ]
    if metric.get("filter"):
        lines.append(f"过滤条件：`{metric['filter']}`")
    if metric.get("default_time_field"):
        lines.append(f"默认时间字段：`{metric['default_time_field']}`")
    return _normalized_text("\n".join(lines))


def _metric_entries(metrics_path: Path, projections_path: Path) -> list[CatalogEntry]:
    """从 metrics authority 派生正文；projection YAML 只提供展示和访问 metadata。"""

    metrics_payload = _load_yaml_mapping(metrics_path)
    metrics = metrics_payload.get("metrics")
    if not isinstance(metrics, dict):
        _fail("source_parse_error", f"{metrics_path} 缺少 metrics mapping")
    projections_payload = _load_yaml_mapping(projections_path)
    projections = projections_payload.get("metric_projections")
    if not isinstance(projections, list):
        _fail("source_parse_error", f"{projections_path} 缺少 metric_projections list")

    entries: list[CatalogEntry] = []
    for index, raw in enumerate(projections):
        source = f"{projections_path}#metric_projections[{index}]"
        if not isinstance(raw, dict):
            _fail("source_parse_error", f"{source} 必须是 mapping")
        metadata = _validated_metadata(raw, source=source, metric=True)
        metric_key = metadata["metric_key"]
        metric = metrics.get(metric_key)
        if not isinstance(metric, dict):
            _fail("metric_key_not_found", f"{source} 引用了不存在的 metric key: {metric_key}")
        authority_ref = f"domain_pack/metrics.yaml#metrics.{metric_key}"
        entries.append(
            _entry(
                metadata,
                authority_ref=authority_ref,
                source_kind="metric_projection",
                source_key=metric_key,
                content=_metric_content(metric_key, metric),
            )
        )
    return entries


def _validate_complete_catalog(entries: list[CatalogEntry]) -> None:
    """全量通过后才允许构造 StagedCatalog，防止部分成功。"""

    seen_revisions: set[tuple[str, str]] = set()
    seen_anchors: set[str] = set()
    seen_identities: set[str] = set()
    for entry in entries:
        revision_identity = (entry.document_key, entry.revision)
        if revision_identity in seen_revisions:
            _fail("duplicate_document_revision", f"重复 document/revision: {revision_identity}")
        if entry.anchor in seen_anchors:
            _fail("duplicate_anchor", f"重复 anchor: {entry.anchor}")
        if entry.content_identity in seen_identities:
            _fail("duplicate_content_identity", f"重复 content identity: {entry.content_identity}")
        seen_revisions.add(revision_identity)
        seen_anchors.add(entry.anchor)
        seen_identities.add(entry.content_identity)


def build_staged_catalog(
    *,
    policy_source_dir: Path = DEFAULT_POLICY_SOURCE_DIR,
    metrics_path: Path = DEFAULT_METRICS_PATH,
    metric_projections_path: Path = DEFAULT_METRIC_PROJECTIONS_PATH,
    recipe: CatalogBuildRecipe = CatalogBuildRecipe(),
) -> StagedCatalog:
    """构建完整 staged catalog；失败时只抛结构化异常，不产生外部写入。"""

    if not recipe.identity.strip():
        _fail("missing_required_field", "build recipe identity 不能为空")
    if not policy_source_dir.is_dir() or not metrics_path.is_file() or not metric_projections_path.is_file():
        _fail("source_not_found", "policy source、metrics 或 metric projections 不完整")

    # 步骤 1：完整读取两类 authority；任一路径异常都会直接中止。----------------------
    entries = [*_policy_entries(policy_source_dir), *_metric_entries(metrics_path, metric_projections_path)]
    if not entries:
        _fail("source_not_found", "没有发现任何 authority source")
    # 步骤 2：稳定排序后做跨来源全局冲突检查。------------------------------------------
    entries.sort(key=lambda item: (item.document_key, item.revision, item.anchor))
    _validate_complete_catalog(entries)

    # 步骤 3：identity 只依赖规范化语义和 recipe，不读取 mtime 或目录遍历顺序。---------
    manifest_records = [entry.manifest_record() for entry in entries]
    corpus_identity = _canonical_hash({"entries": manifest_records})
    if recipe.expected_corpus_identity and recipe.expected_corpus_identity != corpus_identity:
        _fail(
            "content_identity_drift",
            f"期望 {recipe.expected_corpus_identity}，实际 {corpus_identity}",
        )
    build_identity = _canonical_hash({"recipe": recipe.identity, "corpus_identity": corpus_identity})
    return StagedCatalog(entries=tuple(entries), corpus_identity=corpus_identity, build_identity=build_identity)
