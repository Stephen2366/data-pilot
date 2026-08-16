"""M34 retrieval unit 的 offset、identity、边界与 overlap 测试。"""

from __future__ import annotations

from hashlib import sha256

from engine.rag.enterprise_dataset import SourceInstance
from engine.rag.enterprise_parser import NormalizationEvents, NormalizedDocument
from engine.rag.enterprise_units import UnitRecipe, build_retrieval_units


def _document(content: str) -> NormalizedDocument:
    source = SourceInstance(
        source_type="confluence",
        relative_path="confluence/confluence/dsid_00000000000000000000000000000001__x.txt",
        logical_document_id="dsid_00000000000000000000000000000001",
        semantic_name="x",
        byte_size=len(content.encode()),
        content_sha256=sha256(content.encode()).hexdigest(),
        physical_identity="physical-1",
    )
    return NormalizedDocument(
        source_instance=source,
        parser_identity="parser-1",
        title="Title",
        content=content,
        content_sha256=sha256(content.encode()).hexdigest(),
        document_revision="revision-1",
        events=NormalizationEvents(0, 0, 0, 0, 0, 0),
    )


def test_paragraph_units_round_trip_to_normalized_offsets() -> None:
    document = _document("Title\n\nAlpha one.\n\nBeta two.\n\nGamma three.")
    recipe = UnitRecipe("test-pack", "paragraph_pack", max_characters=22)
    units = build_retrieval_units(document, recipe)

    assert len(units) == 3
    for unit in units:
        assert document.content[unit.normalized_start : unit.normalized_end] == unit.content
        assert unit.anchor == f"normalized-char:{unit.normalized_start}-{unit.normalized_end}"
        assert unit.content_sha256 == sha256(unit.content.encode()).hexdigest()


def test_oversized_paragraph_hard_split_still_round_trips() -> None:
    document = _document("Title\n\n" + "x" * 25)
    recipe = UnitRecipe("test-hard-split", "paragraph_pack", max_characters=10)
    units = build_retrieval_units(document, recipe)

    assert max(len(unit.content) for unit in units) <= 10
    assert all(
        document.content[unit.normalized_start : unit.normalized_end] == unit.content
        for unit in units
    )


def test_overlap_changes_identity_and_repeats_only_previous_paragraph() -> None:
    document = _document("Title\n\nAlpha.\n\nBeta.\n\nGamma.")
    plain = UnitRecipe("plain", "paragraph_pack", max_characters=14)
    overlap = UnitRecipe("overlap", "paragraph_pack", max_characters=14, overlap_paragraphs=1)

    plain_units = build_retrieval_units(document, plain)
    overlap_units = build_retrieval_units(document, overlap)
    assert plain.identity != overlap.identity
    assert {unit.unit_identity for unit in plain_units}.isdisjoint(
        unit.unit_identity for unit in overlap_units
    )
    assert len(overlap_units) <= len(plain_units) + 1
