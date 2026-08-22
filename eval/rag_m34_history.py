"""把 M34 completed AnswerFlow artifact 投影为只读 historical 诊断视图。"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from engine.rag.enterprise_answer_eval import ANSWER_EVAL_FORMAT
from engine.rag.enterprise_dataset import canonical_identity
from eval.rag_e2e_contracts import RAGEvalContractError


def import_m34_answer_history(path: Path) -> dict[str, Any]:
    """验证 M34 原始签名后只做汇总；绝不调用 Tool、retriever 或 LLM。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != ANSWER_EVAL_FORMAT or payload.get("status") != "completed":
        raise RAGEvalContractError("rag_m34_history_invalid", "只接受 completed M34 Answer artifact")
    question_ids = payload.get("question_ids") or []
    executions = payload.get("executions") or []
    if [item.get("question_id") for item in executions] != question_ids:
        raise RAGEvalContractError("rag_m34_history_closed_world", "question IDs 不闭合")
    identity_payload = {
        "format": ANSWER_EVAL_FORMAT,
        "dataset_identity": payload.get("dataset_identity"),
        "question_set_identity": payload.get("question_set_identity"),
        "split_identity": payload.get("split_identity"),
        "profile_identity": payload.get("profile_identity"),
        "composer_identity": payload.get("composer_identity"),
        "question_ids": question_ids,
        "executions": executions,
    }
    if payload.get("artifact_identity") != canonical_identity(identity_payload):
        raise RAGEvalContractError("rag_m34_history_hash_mismatch", "M34 artifact identity 不匹配")
    file_hash = sha256(path.read_bytes()).hexdigest()
    overall = dict((payload.get("summaries") or {}).get("overall") or {})
    unavailable = sum(
        (item.get("composer_attempt") or {}).get("status") not in {None, "succeeded"} for item in executions
    )
    return {
        "format": "phase4-rag-m34-historical-view-v1",
        "source": {"path": str(path), "sha256": file_hash, "artifact_identity": payload["artifact_identity"]},
        "runtime_kind": "external-direct-answer-flow",
        "is_product_harness_e2e": False,
        "question_count": len(executions),
        "answer_flow_call_count": sum(int(item.get("answer_flow_calls") or 0) for item in executions),
        "provider_unavailable_count": unavailable,
        "observed_layers": ["retrieval_result", "composer/support", "citation", "exact-fact-string-lower-bound"],
        "not_observed_layers": ["api", "turn", "router", "harness", "selected", "generation-visible", "response-trace-consistency"],
        "summary": overall,
        "boundary": "历史 external 诊断，不能与 M41 business product E2E Gate 或质量分数混算。",
    }
