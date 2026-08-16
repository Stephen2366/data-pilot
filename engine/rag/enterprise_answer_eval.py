"""M34 专用 Answer/Citation Eval：gold 只在一次真实 AnswerFlow 返回后参与评分。"""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from statistics import median
from typing import Any, Mapping, Sequence

from engine.rag.answer_flow import AnswerFlowContractError, RAGAnswerResult
from engine.rag.enterprise_dataset import BenchmarkQuestion, EnterpriseDatasetError, canonical_identity
from engine.rag.evidence import DocumentEvidencePayload

ANSWER_EVAL_FORMAT = "enterprise-rag-answer-eval-v1"


def _normalized_text(value: str) -> str:
    """保守的确定性 scorer：只折叠大小写、Unicode、标点和空白，不做语义猜测。"""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in normalized).split())


def _multiset_coverage(expected: Sequence[str], actual: Sequence[str]) -> dict[str, Any]:
    """按重复次数计算 gold 文档被最终 citation 覆盖的比例。"""
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    covered = sum(min(count, actual_counts[key]) for key, count in expected_counts.items())
    return {
        "covered": covered,
        "expected": len(expected),
        "coverage": covered / len(expected),
        "all_gold": covered == len(expected),
    }


def _cited_logical_documents(result: RAGAnswerResult) -> tuple[str, ...]:
    """只读 ledger 的 cited stage；candidate/generation-visible 不能冒充最终引用。"""

    documents: list[str] = []
    for evidence in result.ledger.evidence:
        if result.ledger.stage_of(evidence.ref.evidence_id) != "cited":
            continue
        payload = evidence.payload
        if not isinstance(payload, DocumentEvidencePayload) or payload.context_coordinates is None:
            raise EnterpriseDatasetError("answer_eval_cited_coordinates_missing", evidence.ref.evidence_id)
        documents.append(payload.context_coordinates.logical_document_id)
    return tuple(documents)


def build_answer_execution(
    *,
    question: BenchmarkQuestion,
    result: RAGAnswerResult | None,
    contract_error: AnswerFlowContractError | None,
    provider_usage_delta: Mapping[str, int],
    composer_attempt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """在运行结束后才读取 gold，并形成可离线复算的一题证据。"""

    if (result is None) == (contract_error is None):
        raise EnterpriseDatasetError("answer_eval_execution_shape_invalid", question.question_id)
    answer = result.answer if result is not None else None
    cited_docs = _cited_logical_documents(result) if result is not None else ()
    normalized_answer = _normalized_text(answer or "")
    fact_checks = [
        {
            "fact": fact,
            "exactly_supported": bool(_normalized_text(fact)) and _normalized_text(fact) in normalized_answer,
        }
        for fact in question.answer_facts
    ]
    document_coverage = _multiset_coverage(question.expected_document_ids, cited_docs)
    return {
        "question_id": question.question_id,
        "question_type": question.question_type,
        "source_types": list(question.source_types),
        "document_cardinality": (
            "multi_document" if len(question.expected_document_ids) > 1 else "single_document"
        ),
        # ★ 这些 gold 字段只在 flow 返回/拒绝后加入，绝不进入 request/context/composer。
        "expected_document_ids": list(question.expected_document_ids),
        "gold_answer": question.gold_answer,
        "answer_facts": list(question.answer_facts),
        "outcome": "answer_result" if result is not None else "contract_rejected",
        "internal_reason_code": result.reason_code if result is not None else contract_error.reason_code,
        "result": result.safe_projection() if result is not None else None,
        "cited_logical_document_ids": list(cited_docs),
        "document_coverage": document_coverage,
        "fact_checks": fact_checks,
        "exact_fact_coverage": (
            sum(item["exactly_supported"] for item in fact_checks) / len(fact_checks)
            if fact_checks
            else 0.0
        ),
        "provider_usage_delta": dict(provider_usage_delta),
        "composer_attempt": dict(composer_attempt) if composer_attempt is not None else None,
        "answer_flow_calls": 1,
    }


def _summary(executions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """汇总完成率、引用覆盖、事实字符串下限、token 和延迟。"""
    if not executions:
        return {"question_count": 0}
    completed = [
        item
        for item in executions
        if item["result"] is not None and item["result"]["answer_status"] == "complete"
    ]
    elapsed = sorted(
        float(item["result"]["diagnostics"]["elapsed_ms"])
        for item in executions
        if item["result"] is not None
    )
    return {
        "question_count": len(executions),
        "answer_complete_rate": round(len(completed) / len(executions), 6),
        "contract_rejected_rate": round(
            sum(item["outcome"] == "contract_rejected" for item in executions) / len(executions), 6
        ),
        "gold_document_all_cited_rate": round(
            sum(item["document_coverage"]["all_gold"] for item in executions) / len(executions), 6
        ),
        "mean_gold_document_coverage": round(
            sum(item["document_coverage"]["coverage"] for item in executions) / len(executions), 6
        ),
        "mean_exact_fact_coverage": round(
            sum(float(item["exact_fact_coverage"]) for item in executions) / len(executions), 6
        ),
        "provider_requests": sum(int(item["provider_usage_delta"].get("request_count", 0)) for item in executions),
        "provider_total_tokens": sum(int(item["provider_usage_delta"].get("total_tokens", 0)) for item in executions),
        "elapsed_ms": {
            "p50": round(median(elapsed), 3) if elapsed else None,
            "p95": round(elapsed[int((len(elapsed) - 1) * 0.95)], 3) if elapsed else None,
            "max": round(max(elapsed), 3) if elapsed else None,
        },
    }


def answer_eval_summaries(executions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """固定 overall/type/cardinality/source 分组，不扩建通用评测平台。"""

    groups: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in executions:
        groups["overall"].append(item)
        groups[f"type:{item['question_type']}"].append(item)
        groups[f"cardinality:{item['document_cardinality']}"].append(item)
        groups[f"source:{'+'.join(item['source_types'])}"].append(item)
    return {key: _summary(values) for key, values in sorted(groups.items())}


def finalize_answer_artifact(
    *,
    dataset_identity: str,
    question_set_identity: str,
    split_identity: str,
    profile_identity: str,
    composer_identity: str,
    question_ids: Sequence[str],
    executions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """只有 180 个唯一题、每题一次 flow 时才签发 completed artifact identity。"""

    ids = [item.get("question_id") for item in executions]
    if ids != list(question_ids) or len(set(ids)) != len(ids):
        raise EnterpriseDatasetError("answer_eval_closed_world_mismatch", "question IDs")
    if any(item.get("answer_flow_calls") != 1 for item in executions):
        raise EnterpriseDatasetError("answer_eval_flow_call_mismatch", "answer_flow_calls")
    identity_payload = {
        "format": ANSWER_EVAL_FORMAT,
        "dataset_identity": dataset_identity,
        "question_set_identity": question_set_identity,
        "split_identity": split_identity,
        "profile_identity": profile_identity,
        "composer_identity": composer_identity,
        "question_ids": list(question_ids),
        "executions": list(executions),
    }
    return {
        **{key: value for key, value in identity_payload.items() if key != "executions"},
        "status": "completed",
        "question_count": len(executions),
        "answer_flow_call_count": len(executions),
        "artifact_identity": canonical_identity(identity_payload),
        "summaries": answer_eval_summaries(executions),
        "executions": list(executions),
    }
