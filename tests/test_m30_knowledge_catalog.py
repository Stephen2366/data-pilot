"""M30 可信原件、staged catalog 与 Text2SQL 隔离合同测试。

全部测试只使用本地文件、确定性 builder 和 SQLite 无关的纯策略，不调用远程模型、
embedding、Milvus 或 LangFuse。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import pytest
import yaml

from engine.nl2sql.planner import QueryPlan, QueryPlanStep, validate_query_plan
from engine.nl2sql.prompt import build_sql_prompt
from engine.nl2sql.schema_loader import DEFAULT_QUERYABLE_TABLE_NAMES, load_domain_schema
from engine.rag import CatalogBuildError, CatalogBuildRecipe, build_staged_catalog
from engine.schema_retrieval.document_builder import build_schema_documents
from engine.schema_retrieval.objects import SchemaGraph
from engine.sql_guard.policy import validate_sql_policy
from engine.sql_guard.rbac import ALL_TABLES, ROLE_POLICIES
from scripts.seed_data import EXPECTED_SEED_COUNTS, _build_knowledge_docs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KB_DOCS = PROJECT_ROOT / "domain_pack" / "kb_docs"
METRICS = PROJECT_ROOT / "domain_pack" / "metrics.yaml"


def _copy_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    """复制 authority fixtures，让失败反例不会修改仓库原件。"""

    policies = tmp_path / "kb_docs"
    shutil.copytree(KB_DOCS, policies)
    metrics = tmp_path / "metrics.yaml"
    shutil.copy2(METRICS, metrics)
    return policies, metrics, policies / "metric_projections.yaml"


def _rewrite_front_matter(path: Path, mutate: Callable[[dict[str, object]], object]) -> None:
    """只改测试副本的 front matter，正文原样保留。"""

    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    metadata_text, body = raw[4:].split("\n---\n", 1)
    metadata = yaml.safe_load(metadata_text)
    mutate(metadata)
    rendered = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{rendered}\n---\n{body}", encoding="utf-8")


def test_default_catalog_is_complete_immutable_staged_and_auditable() -> None:
    catalog = build_staged_catalog()

    assert catalog.lifecycle_status == "staged"
    assert len(catalog.entries) == 22
    assert len(catalog.usable_entries) == 22
    assert catalog.summary()["counts_by_source"] == {"metric_projection": 12, "policy_markdown": 10}
    assert [entry.document_key for entry in catalog.entries] == sorted(entry.document_key for entry in catalog.entries)
    assert all(entry.authority_ref and entry.content_identity and entry.anchor for entry in catalog.entries)
    assert all(entry.public or entry.allowed_roles for entry in catalog.entries)
    assert "content" not in catalog.manifest()["entries"][0]
    with pytest.raises(TypeError):
        catalog.summary()["entry_count"] = 0


def test_metric_entries_are_derived_from_metrics_yaml_without_editable_formula_copy() -> None:
    catalog = build_staged_catalog()
    gmv = next(entry for entry in catalog.entries if entry.document_key == "gmv_metric_note")
    projections_text = (KB_DOCS / "metric_projections.yaml").read_text(encoding="utf-8")

    assert gmv.source_kind == "metric_projection"
    assert gmv.authority_ref == "domain_pack/metrics.yaml#metrics.gmv"
    assert "SUM(orders.order_amount)" in gmv.content
    assert "成交总额" in gmv.content
    assert "formula:" not in projections_text
    assert "description:" not in projections_text


def test_legacy_seed_projection_is_derived_from_the_same_catalog() -> None:
    """方案 B 可以暂留物理表，但不能继续保留可独立编辑的第二份正文。"""

    catalog = build_staged_catalog()
    rows = _build_knowledge_docs()

    assert EXPECTED_SEED_COUNTS["knowledge_docs"] == len(rows) == len(catalog.entries) == 22
    assert [(row.doc_key, row.content) for row in rows] == [
        (entry.document_key, entry.content) for entry in catalog.entries
    ]


def test_identity_ignores_yaml_key_order_but_detects_semantic_change(tmp_path: Path) -> None:
    policies, metrics, projections = _copy_sources(tmp_path)
    baseline = build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)

    metric_payload = yaml.safe_load(metrics.read_text(encoding="utf-8"))
    metrics.write_text(yaml.safe_dump(metric_payload, allow_unicode=True, sort_keys=True), encoding="utf-8")
    reordered = build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    assert reordered.corpus_identity == baseline.corpus_identity

    policy = policies / "invoice-rule.md"
    policy.write_text(policy.read_text(encoding="utf-8").replace("7 天内", "8 天内"), encoding="utf-8")
    changed = build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    assert changed.corpus_identity != baseline.corpus_identity
    with pytest.raises(CatalogBuildError) as exc_info:
        build_staged_catalog(
            policy_source_dir=policies,
            metrics_path=metrics,
            metric_projections_path=projections,
            recipe=CatalogBuildRecipe(expected_corpus_identity=baseline.corpus_identity),
        )
    assert exc_info.value.reason_code == "content_identity_drift"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (lambda item: item.pop("title"), "missing_required_field"),
        (lambda item: item.update(status="draft"), "invalid_enum"),
        (lambda item: item.update(allowed_roles=["root"]), "invalid_acl"),
        (lambda item: item.update(usable=True), "unknown_field"),
    ],
)
def test_invalid_policy_metadata_fails_the_whole_build(
    tmp_path: Path,
    mutation: Callable[[dict[str, object]], object],
    reason_code: str,
) -> None:
    policies, metrics, projections = _copy_sources(tmp_path)
    _rewrite_front_matter(policies / "invoice-rule.md", mutation)

    with pytest.raises(CatalogBuildError) as exc_info:
        build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    assert exc_info.value.reason_code == reason_code


def test_duplicate_revision_anchor_and_content_fail_closed(tmp_path: Path) -> None:
    policies, metrics, projections = _copy_sources(tmp_path)
    original = policies / "invoice-rule.md"

    duplicate_revision = policies / "invoice-copy.md"
    shutil.copy2(original, duplicate_revision)
    with pytest.raises(CatalogBuildError) as exc_info:
        build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    assert exc_info.value.reason_code == "duplicate_document_revision"

    duplicate_revision.unlink()
    duplicate_anchor = policies / "invoice-copy.md"
    shutil.copy2(original, duplicate_anchor)
    _rewrite_front_matter(duplicate_anchor, lambda item: item.update(document_key="invoice_copy", revision="r2"))
    with pytest.raises(CatalogBuildError) as exc_info:
        build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    assert exc_info.value.reason_code == "duplicate_anchor"

    _rewrite_front_matter(duplicate_anchor, lambda item: item.update(anchor="invoice-copy"))
    with pytest.raises(CatalogBuildError) as exc_info:
        build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    assert exc_info.value.reason_code == "duplicate_content_identity"


def test_unknown_metric_key_and_inactive_usable_leak_are_closed(tmp_path: Path) -> None:
    policies, metrics, projections = _copy_sources(tmp_path)
    projection_payload = yaml.safe_load(projections.read_text(encoding="utf-8"))
    projection_payload["metric_projections"][0]["metric_key"] = "missing_metric"
    projections.write_text(yaml.safe_dump(projection_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(CatalogBuildError) as exc_info:
        build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    assert exc_info.value.reason_code == "metric_key_not_found"

    shutil.copy2(KB_DOCS / "metric_projections.yaml", projections)
    _rewrite_front_matter(policies / "invoice-rule.md", lambda item: item.update(status="inactive"))
    catalog = build_staged_catalog(policy_source_dir=policies, metrics_path=metrics, metric_projections_path=projections)
    invoice = next(entry for entry in catalog.entries if entry.document_key == "invoice_rule")
    assert invoice.status == "inactive"
    assert invoice not in catalog.usable_entries
    assert next(item for item in catalog.manifest()["entries"] if item["document_key"] == "invoice_rule")["usable"] is False


def test_text2sql_universe_excludes_knowledge_docs_at_every_gate() -> None:
    schema = load_domain_schema()
    documents = build_schema_documents(schema)
    prompt = build_sql_prompt(question="查询知识库正文", user_role="admin", domain_schema=schema)

    assert set(schema.tables) == set(DEFAULT_QUERYABLE_TABLE_NAMES) == ALL_TABLES
    assert "knowledge_docs" not in schema.tables
    assert all(document.table != "knowledge_docs" for document in documents)
    assert "knowledge_docs" not in prompt
    assert all("knowledge_docs" not in policy.allowed_tables for policy in ROLE_POLICIES.values())

    for role in ROLE_POLICIES:
        result = validate_sql_policy("SELECT content FROM knowledge_docs", user_role=role, domain_schema=schema)
        assert result.is_allowed is False
        assert "knowledge_docs" in (result.blocked_reason or "")

    # 即使模型手工伪造一个包含 knowledge_docs 的 QueryPlan，局部 Schema 门也会先拒绝；
    # 最终 SQL Guard 仍是第二道独立防线。
    plan = QueryPlan(
        plan_id="m30-bypass",
        steps=[
            QueryPlanStep(
                step_id="step_1",
                step_index=1,
                purpose="绕过读取知识正文",
                tables=["knowledge_docs"],
                columns=["knowledge_docs.content"],
                output_columns=["knowledge_docs.content"],
            )
        ],
    )
    validation = validate_query_plan(
        plan,
        schema_graph=SchemaGraph(tables=[], fields={}, metrics=[], relations=[], join_paths=[]),
        domain_schema=schema,
        user_role="admin",
    )
    assert validation.is_valid is False
    assert "missing_table" in validation.issue_tags
