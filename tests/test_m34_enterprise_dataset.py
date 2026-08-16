"""M34 EnterpriseRAG-Bench 原件身份与 closed-world 失败关闭测试。"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from engine.rag.enterprise_dataset import (
    DatasetExpectations,
    DatasetRecipe,
    EnterpriseDatasetError,
    RequiredAsset,
    audit_enterprise_dataset,
)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_fixture(root: Path) -> DatasetRecipe:
    sources = ("confluence", "google_drive", "jira")
    documents = {
        "confluence": [("dsid_00000000000000000000000000000001__policy.txt", b"Policy\nBody")],
        "google_drive": [("dsid_00000000000000000000000000000002__plan.txt", b"Plan\\nBody")],
        "jira": [
            ("dsid_00000000000000000000000000000003__ticket.txt", b"Ticket\nBody"),
            # 同一个 logical ID 的第二份物理文件必须保留为冲突，不能覆盖。
            ("dsid_00000000000000000000000000000003__ticket-copy.txt", b"Other body"),
        ],
    }
    for source_type, items in documents.items():
        for filename, content in items:
            _write(root / "extracted" / source_type / source_type / filename, content)

    question = {
        "question_id": "qst_1",
        "question_type": "semantic",
        "source_types": ["confluence", "jira"],
        "question": "What happened?",
        "expected_doc_ids": [
            "dsid_00000000000000000000000000000001",
            "dsid_00000000000000000000000000000003",
        ],
        "gold_answer": "A policy and ticket explain it.",
        "answer_facts": ["policy", "ticket"],
    }
    # 这条空来源题证明筛选不能使用纯集合 subset 语义。
    empty_source_question = {
        **question,
        "question_id": "qst_empty",
        "source_types": [],
        "expected_doc_ids": [],
    }
    duplicate_logical_question = {
        **question,
        "question_id": "qst_dup",
        "source_types": ["jira"],
        "expected_doc_ids": [
            "dsid_00000000000000000000000000000003",
            "dsid_00000000000000000000000000000003",
        ],
    }
    questions_bytes = (
        json.dumps(question)
        + "\n"
        + json.dumps(empty_source_question)
        + "\n"
        + json.dumps(duplicate_logical_question)
        + "\n"
    ).encode("utf-8")
    assets = {
        "confluence_slice_0001.zip": b"confluence",
        "google_drive_slice_0001.zip": b"drive",
        "jira_slice_0001.zip": b"jira",
        "questions.jsonl": questions_bytes,
    }
    release_assets = []
    required_assets = []
    for name, content in assets.items():
        _write(root / "raw" / name, content)
        digest = sha256(content).hexdigest()
        required_assets.append(RequiredAsset(name=name, size=len(content), sha256=digest))
        release_assets.append({"name": name, "size": len(content), "digest": f"sha256:{digest}"})
    _write(
        root / "raw" / "release-api.json",
        json.dumps({"tag_name": "v-test", "assets": release_assets}).encode("utf-8"),
    )
    return DatasetRecipe(
        recipe_version="test-v1",
        release_tag="v-test",
        source_types=sources,
        question_filter="source_types_nonempty_subset_of_selected_sources",
        required_assets=tuple(required_assets),
        expected=DatasetExpectations(
            source_instances=4,
            selected_questions=2,
            unique_gold_document_ids=2,
            missing_gold_document_ids=0,
            conflicting_logical_document_ids=1,
            source_counts={"confluence": 1, "google_drive": 1, "jira": 2},
        ),
    )


def test_audit_is_stable_and_keeps_logical_physical_identity_separate(tmp_path: Path) -> None:
    recipe = _make_fixture(tmp_path)
    first = audit_enterprise_dataset(tmp_path, recipe)
    second = audit_enterprise_dataset(tmp_path, recipe)

    assert first == second
    assert len(first.source_instances) == 4
    assert len({item.physical_identity for item in first.source_instances}) == 4
    assert first.conflicting_logical_document_ids == (
        "dsid_00000000000000000000000000000003",
    )
    assert [item.question_id for item in first.selected_questions] == ["qst_1", "qst_dup"]
    duplicate_gold = first.selected_questions[1].expected_document_ids
    assert duplicate_gold == (
        "dsid_00000000000000000000000000000003",
        "dsid_00000000000000000000000000000003",
    )
    assert first.missing_gold_document_ids == ()


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("asset_hash", "required_asset_hash_mismatch"),
        ("unknown_source", "unknown_extracted_source"),
        ("invalid_encoding", "invalid_document_encoding"),
        ("gold_missing", "dataset_expectation_mismatch"),
        ("duplicate_question", "duplicate_question_id"),
    ],
)
def test_audit_fails_closed_on_drift(
    tmp_path: Path, mutation: str, reason_code: str
) -> None:
    recipe = _make_fixture(tmp_path)
    if mutation == "asset_hash":
        # 保持字节数不变，隔离验证 hash 漂移，而不是 size 漂移。
        (tmp_path / "raw" / "jira_slice_0001.zip").write_bytes(b"JIRA")
    elif mutation == "unknown_source":
        (tmp_path / "extracted" / "slack").mkdir()
    elif mutation == "invalid_encoding":
        path = next((tmp_path / "extracted" / "jira").rglob("*.txt"))
        path.write_bytes(b"\xff\xfe")
    elif mutation == "gold_missing":
        path = tmp_path / "raw" / "questions.jsonl"
        payload = json.loads(path.read_text().splitlines()[0])
        payload["expected_doc_ids"] = ["dsid_ffffffffffffffffffffffffffffffff"]
        changed = (json.dumps(payload) + "\n").encode()
        path.write_bytes(changed)
        # 让 asset 校验通过，确保测试真正走到 gold closed-world 门。
        digest = sha256(changed).hexdigest()
        assets = list(recipe.required_assets)
        assets[-1] = RequiredAsset("questions.jsonl", len(changed), digest)
        release_path = tmp_path / "raw" / "release-api.json"
        release = json.loads(release_path.read_text())
        release["assets"][-1] = {
            "name": "questions.jsonl",
            "size": len(changed),
            "digest": f"sha256:{digest}",
        }
        release_path.write_text(json.dumps(release))
        recipe = DatasetRecipe(**{**recipe.__dict__, "required_assets": tuple(assets)})
    else:
        path = tmp_path / "raw" / "questions.jsonl"
        first_line = path.read_text().splitlines()[0]
        changed = (first_line + "\n" + first_line + "\n").encode()
        path.write_bytes(changed)
        digest = sha256(changed).hexdigest()
        assets = list(recipe.required_assets)
        assets[-1] = RequiredAsset("questions.jsonl", len(changed), digest)
        release_path = tmp_path / "raw" / "release-api.json"
        release = json.loads(release_path.read_text())
        release["assets"][-1] = {
            "name": "questions.jsonl",
            "size": len(changed),
            "digest": f"sha256:{digest}",
        }
        release_path.write_text(json.dumps(release))
        recipe = DatasetRecipe(**{**recipe.__dict__, "required_assets": tuple(assets)})

    with pytest.raises(EnterpriseDatasetError) as captured:
        audit_enterprise_dataset(tmp_path, recipe)
    assert captured.value.reason_code == reason_code
