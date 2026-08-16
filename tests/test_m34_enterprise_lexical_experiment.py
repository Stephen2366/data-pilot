"""M34 本地 lexical experiment index 的 full-corpus、去重与 gold 隔离测试。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from engine.rag.enterprise_dataset import SourceInstance
from engine.rag.enterprise_parser import NormalizationEvents, NormalizedDocument
from engine.rag.enterprise_units import UnitRecipe
from engine.rag.enterprise_lexical_experiment import SqliteLexicalExperimentIndex


def _document(index: int, content: str) -> NormalizedDocument:
    logical_id = f"dsid_{index:032x}"
    source = SourceInstance(
        source_type="jira",
        relative_path=f"jira/jira/{logical_id}__doc.txt",
        logical_document_id=logical_id,
        semantic_name="doc",
        byte_size=len(content.encode()),
        content_sha256=sha256(content.encode()).hexdigest(),
        physical_identity=f"physical-{index}",
    )
    return NormalizedDocument(
        source_instance=source,
        parser_identity="parser-v1",
        title=content.splitlines()[0],
        content=content,
        content_sha256=sha256(content.encode()).hexdigest(),
        document_revision=f"revision-{index}",
        events=NormalizationEvents(0, 0, 0, 0, 0, 0),
    )


def test_fts_index_searches_units_and_deduplicates_physical_documents(tmp_path: Path) -> None:
    documents = (
        _document(1, "Refund policy\n\nEnterprise refunds need approval.\n\nApproval takes two days."),
        _document(2, "Shipping guide\n\nPackages arrive tomorrow."),
        _document(3, "Approval matrix\n\nSecurity access needs manager approval."),
    )
    recipe = UnitRecipe("test-units", "paragraph_pack", max_characters=40)
    index, build = SqliteLexicalExperimentIndex.build(
        tmp_path / "index.sqlite3",
        documents,
        recipe,
        dataset_identity="dataset-v1",
        parser_identity="parser-v1",
    )
    try:
        matches = index.search("What approval is required for enterprise refunds?")
    finally:
        index.close()

    assert build.document_count == 3
    assert build.unit_count > build.document_count
    assert matches[0].logical_document_id == documents[0].source_instance.logical_document_id
    assert len({item.physical_source_identity for item in matches}) == len(matches)
    assert all(item.anchor.startswith("normalized-char:") for item in matches)
