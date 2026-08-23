"""M42-E reserve 密封、双审、hash 与污染退出测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.phase4b.identity import canonical_hash
from eval.agent_reserve_contracts import (
    ReserveContractError,
    apply_access_event,
    seal_reserve,
    validate_external_store,
)


def _write_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    """构造满足 60 题闭集的最小外部 store，供篡改与状态机测试复用。"""

    records = []
    reviews = []
    for index in range(60):
        difficulty = "basic" if index < 20 else "core" if index < 40 else "hard"
        multi = difficulty == "hard" or (difficulty == "core" and index < 28)
        docs = [f"new-doc-{index:03d}", f"new-doc-pair-{index:03d}"] if multi else [f"new-doc-{index:03d}"]
        row = {
            "reserve_question_id": f"p4b_reserve_{index + 1:03d}", "difficulty": difficulty,
            "question": f"New sealed question {index + 1}?", "expected_doc_ids": docs,
            "gold_answer": f"Gold answer {index + 1}.", "answer_facts": [f"fact-{index + 1}"],
            "source_signature": ["confluence"] if not multi else ["confluence", "jira"],
        }
        records.append(row)
        gold_hash = canonical_hash({"gold_answer": row["gold_answer"], "answer_facts": row["answer_facts"]})
        for reviewer in ("reviewer-a", "reviewer-b"):
            reviews.append({
                "reserve_question_id": row["reserve_question_id"], "reviewer": reviewer,
                "verdict": "approved", "source_hashes": [f"hash-{index}" for _ in docs], "gold_hash": gold_hash,
            })
    reserve = root / "reserve.jsonl"
    review = root / "gold_review.jsonl"
    ledger = root / "access_ledger.jsonl"
    source_pool = root / "source_pool.json"
    reserve.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    review.write_text("\n".join(json.dumps(row) for row in reviews) + "\n", encoding="utf-8")
    ledger.write_text(
        json.dumps({"event": "created", "purpose": "sealed_decision_reserve", "module": "M42"}) + "\n" +
        json.dumps({"event": "sealed", "purpose": "future_B4_decision", "module": "M42"}) + "\n",
        encoding="utf-8",
    )
    source_pool.write_text(json.dumps({
        "selection_identity": "fixture-v1", "exclusion": "fixture historical",
        "sources": [
            {"document_id": f"new-doc-{index:03d}", "source_type": "confluence", "relative_path": f"{index}.txt", "bytes": 1, "sha256": f"hash-{index}"}
            for index in range(60)
        ] + [
            {"document_id": f"new-doc-pair-{index:03d}", "source_type": "jira", "relative_path": f"pair-{index}.txt", "bytes": 1, "sha256": f"hash-{index}"}
            for index in range(20, 60)
        ],
    }), encoding="utf-8")
    return reserve, review, ledger, source_pool


def test_reserve_seals_60_questions_and_external_store_is_hash_bound(tmp_path: Path) -> None:
    reserve, review, ledger, source_pool = _write_fixture(tmp_path)
    manifest = seal_reserve(
        reserve_path=reserve, review_path=review, ledger_path=ledger, source_pool_path=source_pool,
        corpus_identity="corpus-v1", profile_identity="profile-v1",
        excluded_question_ids={"qst_0001"}, excluded_document_ids={"old-doc"},
    )
    assert manifest.distribution == {"basic": 20, "core": 20, "hard": 20}
    assert manifest.multi_document_counts == {"basic": 0, "core": 8, "hard": 20}
    validate_external_store(manifest.payload(), external_root=tmp_path)

    reserve.write_text(reserve.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ReserveContractError, match="artifact_mismatch"):
        validate_external_store(manifest.payload(), external_root=tmp_path)


def test_reserve_access_is_fail_closed_and_contamination_retires_decision_set(tmp_path: Path) -> None:
    reserve, review, ledger, source_pool = _write_fixture(tmp_path)
    manifest = seal_reserve(
        reserve_path=reserve, review_path=review, ledger_path=ledger, source_pool_path=source_pool,
        corpus_identity="corpus-v1", profile_identity="profile-v1",
        excluded_question_ids=set(), excluded_document_ids=set(),
    )
    with pytest.raises(ReserveContractError, match="access_invalid"):
        apply_access_event(manifest, event="first_unseal", module="M45")
    assert apply_access_event(manifest, event="first_unseal", module="M46").decision_status == "unsealed"
    assert apply_access_event(manifest, event="used_for_tuning", module="M45").decision_status == "retired"
