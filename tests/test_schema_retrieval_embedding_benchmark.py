"""Schema Retrieval embedding benchmark tests."""

from __future__ import annotations

from pathlib import Path

from eval.run_schema_retrieval_benchmark import (
    DEFAULT_CASES,
    load_benchmark_cases,
    run_benchmark,
    write_report,
)


def test_load_schema_retrieval_embedding_cases() -> None:
    """retrieval-only benchmark 用例应覆盖语义、关系和 hard negative 场景。"""

    cases = load_benchmark_cases(DEFAULT_CASES)
    categories = {case.category for case in cases}

    assert len(cases) >= 10
    assert {"synonym", "semantic", "relation", "hard_negative"} <= categories
    assert all(case.expected_tables or case.expected_metrics or case.expected_relations for case in cases)


def test_run_schema_retrieval_benchmark_default_backend() -> None:
    """默认 in-memory deterministic 路径可直接跑 benchmark，不依赖 Milvus。"""

    cases = load_benchmark_cases(DEFAULT_CASES)[:3]
    results = run_benchmark(cases, top_k=12)

    assert len(results) == 3
    assert all(0.0 <= result.overall_recall <= 1.0 for result in results)
    assert all(result.keyword_top_docs for result in results)
    assert all(result.vector_top_docs for result in results)
    assert all(result.merged_top_docs for result in results)


def test_run_schema_retrieval_benchmark_can_select_rrf_explicitly() -> None:
    """M21 的 RRF 仅在显式参数下启用，默认 benchmark 不会悄悄换融合策略。"""

    cases = load_benchmark_cases(DEFAULT_CASES)[:2]
    results = run_benchmark(cases, top_k=12, fusion_strategy="rrf")

    assert len(results) == 2
    assert all(0.0 <= result.overall_recall <= 1.0 for result in results)


def test_write_schema_retrieval_benchmark_report(tmp_path: Path) -> None:
    """报告要展示 runtime metadata、case summary 和 top docs，方便比较 embedding。"""

    cases = load_benchmark_cases(DEFAULT_CASES)[:2]
    results = run_benchmark(cases, top_k=8)
    report = tmp_path / "retrieval-report.md"

    write_report(
        results,
        path=report,
        metadata={
            "schema_vector_backend": "inmemory",
            "schema_embedding_provider": "deterministic",
            "fusion_strategy": "rrf",
        },
    )

    text = report.read_text(encoding="utf-8")
    assert "Runtime Metadata" in text
    assert "Case Summary" in text
    assert "Top Docs" in text
    assert "schema_vector_backend" in text
    assert "fusion_strategy" in text
