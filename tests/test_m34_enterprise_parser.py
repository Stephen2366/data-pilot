"""M34 source-aware parser 的结构修复、身份和失败关闭测试。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from engine.rag.enterprise_dataset import EnterpriseDatasetError, SourceInstance
from engine.rag.enterprise_parser import (
    DEFAULT_PARSER_RECIPE,
    ParserRecipe,
    SourceParserPolicy,
    parse_source_document,
)


def _instance(path: Path, source_type: str, content: bytes) -> SourceInstance:
    relative = f"{source_type}/{source_type}/{path.name}"
    return SourceInstance(
        source_type=source_type,
        relative_path=relative,
        logical_document_id=path.name.split("__", 1)[0],
        semantic_name=path.stem.split("__", 1)[1],
        byte_size=len(content),
        content_sha256=sha256(content).hexdigest(),
        physical_identity=f"physical-{source_type}",
    )


@pytest.mark.parametrize("source_type", ["confluence", "google_drive", "jira"])
def test_parser_restores_only_structural_newlines_for_each_source(
    tmp_path: Path, source_type: str
) -> None:
    filename = "dsid_00000000000000000000000000000001__sample.txt"
    content = (
        '\ufeffTitle\r\n\r\nBody\\r\\nNext\\nJSON: {\\"path\\": \\"C:\\\\tmp\\"}'
    ).encode("utf-8")
    path = tmp_path / "extracted" / source_type / source_type / filename
    path.parent.mkdir(parents=True)
    path.write_bytes(content)

    document = parse_source_document(
        tmp_path, _instance(path, source_type, content), DEFAULT_PARSER_RECIPE
    )
    assert document.title == "Title"
    assert document.content == (
        'Title\n\nBody\nNext\nJSON: {\\"path\\": \\"C:\\\\tmp\\"}'
    )
    assert document.events.bom_removed == 1
    assert document.events.actual_crlf_normalized == 2
    assert document.events.literal_crlf_decoded == 1
    assert document.events.literal_lf_decoded == 1
    assert document.document_revision


def test_parser_identity_changes_when_policy_changes() -> None:
    changed = ParserRecipe(
        recipe_version=DEFAULT_PARSER_RECIPE.recipe_version,
        source_policies={
            **DEFAULT_PARSER_RECIPE.source_policies,
            "jira": SourceParserPolicy("jira", decode_literal_newlines=False),
        },
    )
    assert changed.identity != DEFAULT_PARSER_RECIPE.identity


def test_parser_rejects_source_changed_after_audit(tmp_path: Path) -> None:
    source_type = "jira"
    filename = "dsid_00000000000000000000000000000001__sample.txt"
    original = b"Title\n\nBody"
    path = tmp_path / "extracted" / source_type / source_type / filename
    path.parent.mkdir(parents=True)
    path.write_bytes(b"Title\n\nChanged")

    with pytest.raises(EnterpriseDatasetError) as captured:
        parse_source_document(
            tmp_path, _instance(path, source_type, original), DEFAULT_PARSER_RECIPE
        )
    assert captured.value.reason_code == "source_changed_after_audit"
