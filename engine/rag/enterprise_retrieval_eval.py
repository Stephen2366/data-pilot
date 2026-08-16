"""M34 专用 EnterpriseRAG retrieval Eval：一题一次真实 Knowledge Tool。

本模块不做通用评测平台，也不读取 gold 正文/答案。运行时只看到 question；Tool 返回后，
scorer 才用 expected logical document IDs 对实际 Evidence 坐标做 multiset coverage。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from time import perf_counter
from typing import Any, Mapping, Sequence

from engine.governance import TrustedCaller
from engine.rag.enterprise_dataset import (
    BenchmarkQuestion,
    DatasetAudit,
    EnterpriseDatasetError,
    canonical_identity,
)
from engine.rag.evidence import DocumentEvidencePayload
from engine.rag.knowledge_tool import KnowledgeRequest, KnowledgeTool
from engine.rag.retrieval import RetrievalBudget

RETRIEVAL_EVAL_FORMAT = "enterprise-rag-retrieval-eval-v1"


def _coverage(expected: Sequence[str], actual: Sequence[str], k: int) -> dict[str, Any]:
    """计算 top-k gold logical document 的 multiset coverage。"""
    expected_counts = Counter(expected)
    actual_counts = Counter(actual[:k])
    covered = sum(min(count, actual_counts[key]) for key, count in expected_counts.items())
    return {
        "covered": covered,
        "expected": len(expected),
        "coverage": covered / len(expected),
        "any_gold": covered > 0,
        "all_gold": covered == len(expected),
    }


def _summary(executions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """汇总 retrieval coverage、MRR、无结果率和查询延迟。"""
    if not executions:
        return {"question_count": 0}
    result: dict[str, Any] = {"question_count": len(executions)}
    for k in (5, 10, 20):
        values = [item["coverage"][str(k)] for item in executions]
        result[f"at_{k}"] = {
            "mean_gold_coverage": round(
                sum(item["coverage"] for item in values) / len(values), 6
            ),
            "any_gold_rate": round(sum(item["any_gold"] for item in values) / len(values), 6),
            "all_gold_rate": round(sum(item["all_gold"] for item in values) / len(values), 6),
        }
    result["mrr"] = round(
        sum(float(item["reciprocal_rank"]) for item in executions) / len(executions), 6
    )
    result["no_result_rate"] = round(
        sum(not item["actual_matches"] for item in executions) / len(executions), 6
    )
    latencies = sorted(float(item["latency_ms"]) for item in executions)
    result["latency_ms"] = {
        "p50": round(median(latencies), 3),
        "p95": round(latencies[int((len(latencies) - 1) * 0.95)], 3),
        "max": round(max(latencies), 3),
    }
    return result


def _group_summaries(executions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """按题型、来源、文档基数和 gold 原始长度桶分组汇总。"""
    groups: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in executions:
        groups["overall"].append(item)
        groups[f"type:{item['question_type']}"].append(item)
        groups[f"source:{'+'.join(item['source_types'])}"].append(item)
        cardinality = "multi_document" if int(item["expected_document_count"]) > 1 else "single_document"
        groups[f"cardinality:{cardinality}"].append(item)
        groups[f"gold_raw_length:{item['gold_raw_length_bucket']}"].append(item)
    return {key: _summary(values) for key, values in sorted(groups.items())}


def _raw_lengths(audit: DatasetAudit) -> dict[str, int]:
    """按 logical ID 汇总最大 source-instance raw bytes。"""

    maxima: dict[str, int] = {}
    for source in audit.source_instances:
        maxima[source.logical_document_id] = max(
            maxima.get(source.logical_document_id, 0), source.byte_size
        )
    return maxima


def _length_bucket(value: int) -> str:
    """明确这是 raw-byte 工程桶，不冒充 token 或 normalized-char 长度。"""

    return "short_lt_8k" if value < 8000 else "medium_8k_12k" if value < 12000 else "long_ge_12k"


def run_enterprise_retrieval_eval(
    *,
    audit: DatasetAudit,
    question_ids: Sequence[str],
    split_identity: str,
    split_name: str,
    tool: KnowledgeTool,
    caller: TrustedCaller,
    profile_identity: str,
    adapter_identity: str,
    retrieval_recipe_identity: str,
) -> dict[str, Any]:
    """执行一次 closed-world retrieval run；gold 只在 ``retrieve`` 返回后出现。"""

    if not split_identity or not split_name or not question_ids:
        raise EnterpriseDatasetError("retrieval_eval_scope_invalid", split_name)
    question_by_id = {item.question_id: item for item in audit.selected_questions}
    if len(set(question_ids)) != len(question_ids) or not set(question_ids) <= set(question_by_id):
        raise EnterpriseDatasetError("retrieval_eval_question_mismatch", split_name)
    raw_lengths = _raw_lengths(audit)
    executions: list[dict[str, Any]] = []
    started = perf_counter()
    for ordinal, question_id in enumerate(question_ids, start=1):
        question: BenchmarkQuestion = question_by_id[question_id]
        query_started = perf_counter()
        outcome = tool.retrieve(
            KnowledgeRequest(
                question=question.question,
                caller=caller,
                purpose="answer_evidence",
                run_id=f"m34-retrieval-{split_name}-{ordinal:03d}-{question_id}",
                budget=RetrievalBudget(max_candidates=20, max_selected=20),
            )
        )
        latency_ms = (perf_counter() - query_started) * 1000
        matches: list[dict[str, Any]] = []
        for evidence in outcome.selected_evidence:
            if not isinstance(evidence.payload, DocumentEvidencePayload):
                raise EnterpriseDatasetError("retrieval_eval_evidence_invalid", question_id)
            coordinates = evidence.payload.context_coordinates
            if coordinates is None:
                raise EnterpriseDatasetError("retrieval_eval_coordinates_missing", question_id)
            matches.append(
                {
                    "logical_document_id": coordinates.logical_document_id,
                    "physical_source_identity": coordinates.physical_source_identity,
                    "source_type": coordinates.source_type,
                    "unit_identity": coordinates.unit_identity,
                    "anchor": evidence.ref.anchor,
                    "content_identity": evidence.ref.content_identity,
                }
            )
        actual = tuple(item["logical_document_id"] for item in matches)
        first_gold = next(
            (rank for rank, logical_id in enumerate(actual, start=1) if logical_id in question.expected_document_ids),
            None,
        )
        expected_lengths = [raw_lengths[logical_id] for logical_id in set(question.expected_document_ids)]
        longest = max(expected_lengths)
        executions.append(
            {
                "question_id": question_id,
                "question_type": question.question_type,
                "source_types": list(question.source_types),
                "expected_document_ids": list(question.expected_document_ids),
                "expected_document_count": len(question.expected_document_ids),
                "gold_raw_length_bucket": _length_bucket(longest),
                "execution_outcome": outcome.execution_outcome,
                "reason_code": outcome.reason_code,
                "adapter_calls": outcome.diagnostics.adapter_calls,
                "latency_ms": round(latency_ms, 3),
                "actual_matches": matches,
                "coverage": {str(k): _coverage(question.expected_document_ids, actual, k) for k in (5, 10, 20)},
                "reciprocal_rank": 0.0 if first_gold is None else 1.0 / first_gold,
            }
        )
    identity_payload = {
        "format": RETRIEVAL_EVAL_FORMAT,
        "dataset_identity": audit.dataset_identity,
        "question_set_identity": audit.question_set_identity,
        "split_identity": split_identity,
        "split_name": split_name,
        "profile_identity": profile_identity,
        "adapter_identity": adapter_identity,
        "retrieval_recipe_identity": retrieval_recipe_identity,
        "executions": [
            {key: value for key, value in item.items() if key != "latency_ms"}
            for item in executions
        ],
    }
    artifact = {
        **{key: value for key, value in identity_payload.items() if key != "executions"},
        "status": "completed",
        "question_count": len(executions),
        "tool_call_count": len(executions),
        "elapsed_seconds": round(perf_counter() - started, 6),
        "artifact_identity": canonical_identity(identity_payload),
        "summaries": _group_summaries(executions),
        "executions": executions,
    }
    validate_enterprise_retrieval_artifact(artifact, question_ids)
    return artifact


def validate_enterprise_retrieval_artifact(
    artifact: Mapping[str, Any], expected_question_ids: Sequence[str]
) -> None:
    """拒绝缺题、多题、重复运行、非单次 Tool 调用和 identity 漂移。"""

    executions = artifact.get("executions")
    if artifact.get("format") != RETRIEVAL_EVAL_FORMAT or artifact.get("status") != "completed":
        raise EnterpriseDatasetError("retrieval_eval_artifact_invalid", "format/status")
    if not isinstance(executions, list):
        raise EnterpriseDatasetError("retrieval_eval_artifact_invalid", "executions")
    ids = [item.get("question_id") for item in executions]
    if ids != list(expected_question_ids) or len(set(ids)) != len(ids):
        raise EnterpriseDatasetError("retrieval_eval_closed_world_mismatch", "question IDs")
    if artifact.get("question_count") != len(ids) or artifact.get("tool_call_count") != len(ids):
        raise EnterpriseDatasetError("retrieval_eval_closed_world_mismatch", "counts")
    if any(item.get("adapter_calls") != 1 for item in executions):
        raise EnterpriseDatasetError("retrieval_eval_tool_call_mismatch", "adapter calls")
    identity_payload = {
        "format": artifact["format"],
        "dataset_identity": artifact["dataset_identity"],
        "question_set_identity": artifact["question_set_identity"],
        "split_identity": artifact["split_identity"],
        "split_name": artifact["split_name"],
        "profile_identity": artifact["profile_identity"],
        "adapter_identity": artifact["adapter_identity"],
        "retrieval_recipe_identity": artifact["retrieval_recipe_identity"],
        "executions": [
            {key: value for key, value in item.items() if key != "latency_ms"}
            for item in executions
        ],
    }
    if canonical_identity(identity_payload) != artifact.get("artifact_identity"):
        raise EnterpriseDatasetError("retrieval_eval_artifact_hash_mismatch", "artifact")
