"""M34-B full-corpus 本地 lexical unit 候选实验。

这是冻结 dev split 上的离线选择证据，不是 Knowledge Tool 的生产 adapter。它不读取
gold 正文、不按 expected source 过滤，也不会修改 business active release。M34-C 只有在
用户确认 profile/index 方案后，才把选中的 recipe 接入正式 lifecycle。
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence

from engine.rag.enterprise_cases import EnterpriseCaseSplit
from engine.rag.enterprise_dataset import (
    BenchmarkQuestion,
    DatasetAudit,
    EnterpriseDatasetError,
    canonical_identity,
)
from engine.rag.enterprise_parser import (
    DEFAULT_PARSER_RECIPE,
    NormalizedDocument,
    ParserRecipe,
    iter_normalized_documents,
)
from engine.rag.enterprise_units import UnitRecipe, build_retrieval_units


_QUERY_TOKEN = re.compile(r"[A-Za-z0-9_]+")
LEXICAL_BACKEND_IDENTITY = "sqlite-fts5-unicode61-or-bm25-v1"


@dataclass(frozen=True)
class LexicalDocumentMatch:
    """按最佳 unit 排序后的物理文档命中。"""

    rank: int
    logical_document_id: str
    physical_source_identity: str
    source_type: str
    unit_identity: str
    anchor: str
    score: float


@dataclass(frozen=True)
class LexicalIndexBuild:
    index_identity: str
    unit_count: int
    document_count: int
    build_seconds: float
    index_bytes: int


class SqliteLexicalExperimentIndex:
    """仅服务 M34 候选实验的本地 FTS5 索引。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection = sqlite3.connect(path)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SqliteLexicalExperimentIndex":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @classmethod
    def build(
        cls,
        path: Path,
        documents: Iterable[NormalizedDocument],
        unit_recipe: UnitRecipe,
        dataset_identity: str,
        parser_identity: str,
    ) -> tuple["SqliteLexicalExperimentIndex", LexicalIndexBuild]:
        if path.exists():
            raise EnterpriseDatasetError("lexical_index_path_exists", str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute(
                """
                CREATE TABLE units (
                    row_id INTEGER PRIMARY KEY,
                    unit_identity TEXT NOT NULL UNIQUE,
                    logical_document_id TEXT NOT NULL,
                    physical_source_identity TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    anchor TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE VIRTUAL TABLE units_fts USING fts5(content, content='', tokenize='unicode61')"
            )
            row_id = 0
            document_count = 0
            metadata_batch: list[tuple[Any, ...]] = []
            fts_batch: list[tuple[Any, ...]] = []
            for document in documents:
                document_count += 1
                for unit in build_retrieval_units(document, unit_recipe):
                    row_id += 1
                    metadata_batch.append(
                        (
                            row_id,
                            unit.unit_identity,
                            unit.logical_document_id,
                            unit.physical_source_identity,
                            unit.source_type,
                            unit.anchor,
                        )
                    )
                    fts_batch.append((row_id, unit.content))
                    if len(metadata_batch) >= 1000:
                        connection.executemany(
                            "INSERT INTO units VALUES (?, ?, ?, ?, ?, ?)", metadata_batch
                        )
                        connection.executemany(
                            "INSERT INTO units_fts(rowid, content) VALUES (?, ?)", fts_batch
                        )
                        metadata_batch.clear()
                        fts_batch.clear()
            if metadata_batch:
                connection.executemany(
                    "INSERT INTO units VALUES (?, ?, ?, ?, ?, ?)", metadata_batch
                )
                connection.executemany(
                    "INSERT INTO units_fts(rowid, content) VALUES (?, ?)", fts_batch
                )
            connection.commit()
        except Exception:
            connection.close()
            raise
        connection.close()

        index_identity = canonical_identity(
            {
                "backend": LEXICAL_BACKEND_IDENTITY,
                "dataset_identity": dataset_identity,
                "parser_identity": parser_identity,
                "unit_recipe_identity": unit_recipe.identity,
                "unit_count": row_id,
                "document_count": document_count,
            }
        )
        build = LexicalIndexBuild(
            index_identity=index_identity,
            unit_count=row_id,
            document_count=document_count,
            build_seconds=round(time.perf_counter() - started, 6),
            index_bytes=path.stat().st_size,
        )
        return cls(path), build

    def search(
        self,
        question: str,
        *,
        max_unit_matches: int = 200,
        max_documents: int = 50,
    ) -> tuple[LexicalDocumentMatch, ...]:
        """一题只执行一次 FTS 查询，再按最佳 unit 去重物理文档。"""

        tokens = [token.lower() for token in _QUERY_TOKEN.findall(question)]
        tokens = list(dict.fromkeys(token for token in tokens if len(token) > 1))
        if not tokens:
            return ()
        # 每个 token 单独加引号，用户问题无法注入 FTS5 操作符。
        expression = " OR ".join(f'"{token}"' for token in tokens)
        rows = self._connection.execute(
            """
            SELECT u.logical_document_id, u.physical_source_identity, u.source_type,
                   u.unit_identity, u.anchor, bm25(units_fts) AS score
            FROM units_fts
            JOIN units AS u ON u.row_id = units_fts.rowid
            WHERE units_fts MATCH ?
            ORDER BY score ASC, u.unit_identity ASC
            LIMIT ?
            """,
            (expression, max_unit_matches),
        ).fetchall()
        selected: list[LexicalDocumentMatch] = []
        seen_physical: set[str] = set()
        for row in rows:
            physical_identity = str(row[1])
            if physical_identity in seen_physical:
                continue
            seen_physical.add(physical_identity)
            selected.append(
                LexicalDocumentMatch(
                    rank=len(selected) + 1,
                    logical_document_id=str(row[0]),
                    physical_source_identity=physical_identity,
                    source_type=str(row[2]),
                    unit_identity=str(row[3]),
                    anchor=str(row[4]),
                    score=float(row[5]),
                )
            )
            if len(selected) >= max_documents:
                break
        return tuple(selected)


def _coverage(expected_ids: Sequence[str], matches: Sequence[LexicalDocumentMatch], k: int) -> dict[str, Any]:
    expected = Counter(expected_ids)
    actual = Counter(match.logical_document_id for match in matches[:k])
    covered = sum(min(count, actual[logical_id]) for logical_id, count in expected.items())
    return {
        "covered": covered,
        "expected": sum(expected.values()),
        "coverage": covered / sum(expected.values()),
        "any_gold": covered > 0,
        "all_gold": covered == sum(expected.values()),
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * percentile)]


def _summarize(executions: Sequence[dict[str, Any]], ks: Sequence[int]) -> dict[str, Any]:
    summary: dict[str, Any] = {"question_count": len(executions)}
    for k in ks:
        observations = [item["coverage"][str(k)] for item in executions]
        summary[f"at_{k}"] = {
            "mean_gold_coverage": round(
                sum(item["coverage"] for item in observations) / len(observations), 6
            ),
            "any_gold_rate": round(
                sum(item["any_gold"] for item in observations) / len(observations), 6
            ),
            "all_gold_rate": round(
                sum(item["all_gold"] for item in observations) / len(observations), 6
            ),
        }
    reciprocal_ranks = [item["reciprocal_rank"] for item in executions]
    summary["mrr"] = round(sum(reciprocal_ranks) / len(reciprocal_ranks), 6)
    latencies = [item["latency_ms"] for item in executions]
    summary["latency_ms"] = {
        "p50": round(median(latencies), 3),
        "p95": round(_percentile(latencies, 0.95), 3),
        "max": round(max(latencies, default=0.0), 3),
    }
    return summary


def run_lexical_dev_experiment(
    audit: DatasetAudit,
    split: EnterpriseCaseSplit,
    unit_recipe: UnitRecipe,
    index_path: Path,
    *,
    parser_recipe: ParserRecipe = DEFAULT_PARSER_RECIPE,
    ks: tuple[int, ...] = (5, 10, 20),
) -> dict[str, Any]:
    """完整 corpus 建一次索引，对冻结的 60 dev 题各查询一次。"""

    question_by_id = {item.question_id: item for item in audit.selected_questions}
    dev_questions = [question_by_id[item] for item in split.diagnostic_dev_question_ids]
    index, build = SqliteLexicalExperimentIndex.build(
        index_path,
        iter_normalized_documents(audit, parser_recipe),
        unit_recipe,
        audit.dataset_identity,
        parser_recipe.identity,
    )
    try:
        executions: list[dict[str, Any]] = []
        for question in dev_questions:
            started = time.perf_counter()
            matches = index.search(question.question)
            latency_ms = (time.perf_counter() - started) * 1000
            first_gold_rank = next(
                (
                    match.rank
                    for match in matches
                    if match.logical_document_id in set(question.expected_document_ids)
                ),
                None,
            )
            executions.append(
                {
                    "question_id": question.question_id,
                    "question_type": question.question_type,
                    "source_types": list(question.source_types),
                    "expected_document_count": len(question.expected_document_ids),
                    "retrieved_documents": [
                        {
                            "rank": match.rank,
                            "logical_document_id": match.logical_document_id,
                            "physical_source_identity": match.physical_source_identity,
                            "source_type": match.source_type,
                            "unit_identity": match.unit_identity,
                            "anchor": match.anchor,
                            "score": match.score,
                        }
                        for match in matches
                    ],
                    "coverage": {
                        str(k): _coverage(question.expected_document_ids, matches, k)
                        for k in ks
                    },
                    "reciprocal_rank": 0.0 if first_gold_rank is None else 1 / first_gold_rank,
                    "latency_ms": round(latency_ms, 6),
                }
            )
    finally:
        index.close()

    semantic = [item for item in executions if item["question_type"] == "semantic"]
    multi = [item for item in executions if item["expected_document_count"] > 1]
    artifact = {
        "artifact_version": "enterprise-lexical-dev-experiment-v1",
        "lifecycle_status": "completed",
        "dataset_identity": audit.dataset_identity,
        "corpus_identity": audit.corpus_identity,
        "question_set_identity": audit.question_set_identity,
        "split_identity": split.split_identity,
        "split": "diagnostic_dev",
        "parser_identity": parser_recipe.identity,
        "unit_recipe_version": unit_recipe.recipe_version,
        "unit_recipe_identity": unit_recipe.identity,
        "backend_identity": LEXICAL_BACKEND_IDENTITY,
        "index_build": build.__dict__,
        "query_protocol": {
            "max_unit_matches": 200,
            "max_documents": 50,
            "ks": list(ks),
            "source_filtering": "none",
            "gold_in_runtime": False,
        },
        "summary": {
            "overall": _summarize(executions, ks),
            "semantic": _summarize(semantic, ks),
            "multi_document": _summarize(multi, ks),
        },
        "executions": executions,
    }
    unsigned = {**artifact}
    artifact["artifact_identity"] = canonical_identity(unsigned)
    return artifact
