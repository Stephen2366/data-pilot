"""M32 deterministic retrieval adapter 的可复现、预算和边界合同。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.rag.catalog import CatalogEntry
from engine.rag.release import load_active_release
from engine.rag.retrieval import (
    DeterministicLexicalRetrievalAdapter,
    RetrievalAdapterError,
    RetrievalBudget,
    query_fingerprint,
)


def _active_entries() -> tuple[CatalogEntry, ...]:
    return load_active_release()[1].entries


def test_deterministic_adapter_repeats_same_gold_order_and_runtime_identity() -> None:
    adapter = DeterministicLexicalRetrievalAdapter()
    kwargs = {
        "question": "质量问题退款需要提供哪些材料？",
        "confirmed_conditions": (),
        "entries": _active_entries(),
        "limit": 5,
    }

    first = adapter.retrieve(**kwargs)
    second = adapter.retrieve(**kwargs)

    assert first == second
    assert first.matches[0].document_key == "refund_policy_quality"
    assert first.matches[0].rank == 1
    assert first.adapter_identity == "knowledge-deterministic-lexical-v1"
    assert first.query_fingerprint == query_fingerprint(kwargs["question"])


def test_metric_title_and_confirmed_conditions_participate_in_retrieval() -> None:
    batch = DeterministicLexicalRetrievalAdapter().retrieve(
        question="这个口径怎么算？",
        confirmed_conditions=("GMV 指标定义",),
        entries=_active_entries(),
        limit=3,
    )
    assert batch.matches[0].document_key == "gmv_metric_note"


def test_no_candidate_is_an_empty_batch_not_a_backend_error() -> None:
    batch = DeterministicLexicalRetrievalAdapter().retrieve(
        question="平台有没有五年整机保修？",
        confirmed_conditions=(),
        entries=_active_entries(),
        limit=3,
    )
    assert batch.matches == ()


def test_adapter_rejects_duplicate_entry_identity_and_invalid_budget() -> None:
    entry = _active_entries()[0]
    adapter = DeterministicLexicalRetrievalAdapter()
    with pytest.raises(RetrievalAdapterError) as duplicate:
        adapter.retrieve(
            question="GMV",
            confirmed_conditions=(),
            entries=(entry, replace(entry)),
            limit=3,
        )
    assert duplicate.value.reason_code == "retrieval_entry_duplicate"

    with pytest.raises(RetrievalAdapterError, match="retrieval_budget_invalid"):
        RetrievalBudget(max_candidates=1, max_selected=2)


def test_equal_score_order_does_not_depend_on_input_order() -> None:
    base = _active_entries()[0]
    left = replace(
        base,
        document_key="a-policy",
        revision="1",
        title="同一规则",
        anchor="a",
        content="同一规则正文",
        content_identity="hash-a",
    )
    right = replace(
        base,
        document_key="b-policy",
        revision="1",
        title="同一规则",
        anchor="b",
        content="同一规则正文",
        content_identity="hash-b",
    )
    adapter = DeterministicLexicalRetrievalAdapter()
    forward = adapter.retrieve(
        question="同一规则", confirmed_conditions=(), entries=(left, right), limit=2
    )
    reverse = adapter.retrieve(
        question="同一规则", confirmed_conditions=(), entries=(right, left), limit=2
    )
    assert forward == reverse
    assert [item.document_key for item in forward.matches] == ["a-policy", "b-policy"]
