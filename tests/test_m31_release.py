"""M31 immutable release、active pointer、故障保持与安全回滚。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from engine.rag.catalog import StagedCatalog, build_staged_catalog
from engine.rag.release import (
    G3Approval,
    ReleaseError,
    activate_release,
    build_candidate_release,
    inspect_release_state,
    load_active_release,
    load_release,
    rollback_active_release,
)


APPROVAL = G3Approval(decision="A", approved_by_ref="user-confirmed-thread", approved_at="2026-08-13")


def _changed_staged(source: StagedCatalog) -> StagedCatalog:
    changed = replace(source.entries[0], title=source.entries[0].title + " v2")
    # 测试只需要第二个合法 identity；复用 builder 的公开形状，具体 identity 不冒充正式 authority hash。
    return StagedCatalog(
        entries=(changed, *source.entries[1:]), corpus_identity="changed-corpus", build_identity="changed-build"
    )


def test_candidate_is_deterministic_immutable_and_reloadable(tmp_path: Path) -> None:
    staged = build_staged_catalog()
    first = build_candidate_release(staged=staged, root=tmp_path)
    second = build_candidate_release(staged=staged, root=tmp_path)
    assert first == second == load_release(root=tmp_path, release_identity=first.release_identity)
    assert inspect_release_state(root=tmp_path)["active"] is False
    assert len(list((tmp_path / "releases").glob("*.json"))) == 1


def test_hash_tamper_and_partial_json_never_become_active(tmp_path: Path) -> None:
    staged = build_staged_catalog()
    bundle = build_candidate_release(staged=staged, root=tmp_path)
    path = tmp_path / "releases" / f"{bundle.release_identity}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["content"] += "tampered"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ReleaseError, match="release_content_hash_mismatch"):
        load_release(root=tmp_path, release_identity=bundle.release_identity)
    assert inspect_release_state(root=tmp_path)["active"] is False

    path.write_text("{", encoding="utf-8")
    with pytest.raises(ReleaseError, match="release_unavailable"):
        load_release(root=tmp_path, release_identity=bundle.release_identity)


def test_pointer_replace_failure_preserves_old_active(tmp_path: Path) -> None:
    staged = build_staged_catalog()
    bundle = build_candidate_release(staged=staged, root=tmp_path)
    old = activate_release(bundle=bundle, staged=staged, approval=APPROVAL, root=tmp_path)

    # 用不同 recipe 得到同 corpus 的新 candidate，模拟候选升级但 pointer replace 中断。
    candidate = build_candidate_release(staged=staged, root=tmp_path, recipe_identity="release-recipe-v2")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected pointer failure")

    with pytest.raises(OSError, match="injected pointer failure"):
        activate_release(
            bundle=candidate, staged=staged, approval=APPROVAL, root=tmp_path, replace=fail_replace
        )
    current, loaded = load_active_release(root=tmp_path)
    assert current == old
    assert loaded.release_identity == bundle.release_identity


def test_faulty_replace_that_corrupts_target_then_raises_still_restores_old_pointer(tmp_path: Path) -> None:
    staged = build_staged_catalog()
    first = build_candidate_release(staged=staged, root=tmp_path)
    old = activate_release(bundle=first, staged=staged, approval=APPROVAL, root=tmp_path)
    second = build_candidate_release(staged=staged, root=tmp_path, recipe_identity="release-recipe-v2")

    def corrupt_then_fail(_source: Path, target: Path) -> None:
        target.write_text("{}", encoding="utf-8")
        raise OSError("injected after target corruption")

    with pytest.raises(OSError, match="after target corruption"):
        activate_release(
            bundle=second, staged=staged, approval=APPROVAL, root=tmp_path, replace=corrupt_then_fail
        )
    assert load_active_release(root=tmp_path)[0] == old


def test_restart_load_fails_closed_when_active_bundle_is_corrupt(tmp_path: Path) -> None:
    staged = build_staged_catalog()
    bundle = build_candidate_release(staged=staged, root=tmp_path)
    activate_release(bundle=bundle, staged=staged, approval=APPROVAL, root=tmp_path)
    path = tmp_path / "releases" / f"{bundle.release_identity}.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ReleaseError, match="release_closed_world_invalid"):
        load_active_release(root=tmp_path)


def test_explicit_rollback_requires_previous_to_match_current_authority(tmp_path: Path) -> None:
    staged = build_staged_catalog()
    first = build_candidate_release(staged=staged, root=tmp_path)
    activate_release(bundle=first, staged=staged, approval=APPROVAL, root=tmp_path)
    second = build_candidate_release(staged=staged, root=tmp_path, recipe_identity="release-recipe-v2")
    pointer = activate_release(bundle=second, staged=staged, approval=APPROVAL, root=tmp_path)
    assert pointer.previous_release_identity == first.release_identity

    restored = rollback_active_release(current_authority=staged, approval=APPROVAL, root=tmp_path)
    assert restored.current_release_identity == first.release_identity
    assert restored.previous_release_identity == second.release_identity


def test_rollback_does_not_resurrect_revoked_or_changed_authority(tmp_path: Path) -> None:
    staged = build_staged_catalog()
    first = build_candidate_release(staged=staged, root=tmp_path)
    activate_release(bundle=first, staged=staged, approval=APPROVAL, root=tmp_path)
    second = build_candidate_release(staged=staged, root=tmp_path, recipe_identity="release-recipe-v2")
    activate_release(bundle=second, staged=staged, approval=APPROVAL, root=tmp_path)

    changed_entry = replace(staged.entries[0], status="revoked")
    changed_authority = StagedCatalog(
        entries=(changed_entry, *staged.entries[1:]), corpus_identity="changed", build_identity="changed"
    )
    with pytest.raises(ReleaseError, match="release_authority_mismatch"):
        rollback_active_release(current_authority=changed_authority, approval=APPROVAL, root=tmp_path)
    assert load_active_release(root=tmp_path)[0].current_release_identity == second.release_identity
