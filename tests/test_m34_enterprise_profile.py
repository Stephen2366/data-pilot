"""M34 external profile 的 immutable build、verify、switch 与失败保留测试。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from engine.rag.enterprise_dataset import DatasetAudit, DatasetExpectations, DatasetRecipe, SourceInstance
from engine.rag.enterprise_profile import (
    ExternalProfileError,
    activate_external_profile,
    build_candidate_external_profile,
    load_active_external_profile,
    verify_external_profile,
)
from engine.rag.enterprise_units import UnitRecipe


def _audit(tmp_path: Path) -> DatasetAudit:
    content = b"Title\n\nAlpha policy paragraph.\n\nBeta details and approval."
    filename = "dsid_00000000000000000000000000000001__sample.txt"
    path = tmp_path / "dataset" / "extracted" / "confluence" / "confluence" / filename
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    source = SourceInstance(
        source_type="confluence",
        relative_path=f"confluence/confluence/{filename}",
        logical_document_id="dsid_00000000000000000000000000000001",
        semantic_name="sample",
        byte_size=len(content),
        content_sha256=sha256(content).hexdigest(),
        physical_identity="physical-1",
    )
    recipe = DatasetRecipe(
        recipe_version="dataset-test-v1",
        release_tag="v-test",
        source_types=("confluence",),
        question_filter="source_types_nonempty_subset_of_selected_sources",
        required_assets=(),
        expected=DatasetExpectations(1, 0, 0, 0, 0, {"confluence": 1}),
    )
    return DatasetAudit(
        recipe=recipe,
        dataset_root=tmp_path / "dataset",
        source_instances=(source,),
        selected_questions=(),
        conflicting_logical_document_ids=(),
        missing_gold_document_ids=(),
        corpus_identity="corpus-test",
        question_set_identity="questions-test",
        dataset_identity="dataset-test",
    )


def test_candidate_build_is_immutable_reloadable_and_safe_to_reuse(tmp_path: Path) -> None:
    audit = _audit(tmp_path)
    root = tmp_path / "profiles"
    recipe = UnitRecipe("unit-test-v1", "paragraph_pack", max_characters=32)

    first = build_candidate_external_profile(root=root, audit=audit, unit_recipe=recipe)
    second = build_candidate_external_profile(root=root, audit=audit, unit_recipe=recipe)
    loaded = verify_external_profile(root=root, profile_identity=first.profile_identity)

    assert first == second == loaded
    assert first.document_count == 1
    assert first.unit_count > 1
    assert first.database_bytes > 0


def test_switch_keeps_previous_and_corrupt_candidate_cannot_replace_active(tmp_path: Path) -> None:
    audit = _audit(tmp_path)
    root = tmp_path / "profiles"
    first = build_candidate_external_profile(
        root=root,
        audit=audit,
        unit_recipe=UnitRecipe("unit-test-small", "paragraph_pack", max_characters=24),
    )
    second = build_candidate_external_profile(
        root=root,
        audit=audit,
        unit_recipe=UnitRecipe("unit-test-large", "paragraph_pack", max_characters=48),
    )
    activate_external_profile(root=root, profile_identity=first.profile_identity)
    pointer, _ = activate_external_profile(root=root, profile_identity=second.profile_identity)
    assert pointer.previous_profile_identity == first.profile_identity

    database = root / first.profile_identity / first.database_file
    database.write_bytes(database.read_bytes() + b"tampered")
    with pytest.raises(ExternalProfileError) as captured:
        activate_external_profile(root=root, profile_identity=first.profile_identity)
    assert captured.value.reason_code == "profile_database_size_mismatch"
    active_pointer, active_manifest = load_active_external_profile(root=root)
    assert active_pointer.active_profile_identity == second.profile_identity
    assert active_manifest.profile_identity == second.profile_identity
