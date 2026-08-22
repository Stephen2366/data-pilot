"""把 M34 completed AnswerFlow artifact 投影为只读 historical 诊断视图。"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Iterable

from engine.rag.enterprise_answer_eval import ANSWER_EVAL_FORMAT
from engine.rag.enterprise_retrieval_eval import validate_enterprise_retrieval_artifact
from engine.rag.enterprise_dataset import canonical_identity
from eval.rag_e2e_contracts import RAGEvalContractError


def _layer(status: str, reason: str, **evidence: Any) -> dict[str, Any]:
    """统一旧证据的三态层；缺少旧字段只能 not_observed，不能猜测。"""

    return {"status": status, "reason": reason, **evidence}


def _group_summary(cases: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按冻结 split 与原生 strata 汇总首个失败层，不制造综合分。"""

    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups["overall"].append(case)
        groups[f"partition:{case['partition']}"].append(case)
        groups[f"type:{case['question_type']}"].append(case)
        groups[f"cardinality:{case['document_cardinality']}"].append(case)
        groups[f"source:{'+'.join(case['source_types'])}"].append(case)
    return {
        name: {
            "question_count": len(items),
            "primary_failure_counts": dict(sorted(Counter(item["primary_failure"] for item in items).items())),
        }
        for name, items in sorted(groups.items())
    }


def import_m34_answer_history(
    path: Path,
    *,
    retrieval_paths: tuple[Path, ...] = (),
    split_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """验证 M34 原始签名后逐题投影；绝不调用 Tool、retriever 或 LLM。"""

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
    # 步骤 2：可选合并既有 dev/held-out retrieval artifact；它们必须同源且闭集。=====
    retrieval_by_id: dict[str, dict[str, Any]] = {}
    retrieval_sources: list[dict[str, str]] = []
    for retrieval_path in retrieval_paths:
        retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
        ids = [str(item.get("question_id")) for item in retrieval.get("executions") or ()]
        validate_enterprise_retrieval_artifact(retrieval, ids)
        if (
            retrieval.get("dataset_identity") != payload.get("dataset_identity")
            or retrieval.get("question_set_identity") != payload.get("question_set_identity")
            or retrieval.get("split_identity") != payload.get("split_identity")
            or retrieval.get("profile_identity") != payload.get("profile_identity")
        ):
            raise RAGEvalContractError("rag_m34_history_identity_mismatch", str(retrieval_path))
        for item in retrieval["executions"]:
            question_id = str(item["question_id"])
            if question_id in retrieval_by_id:
                raise RAGEvalContractError("rag_m34_history_retrieval_duplicate", question_id)
            retrieval_by_id[question_id] = dict(item)
        retrieval_sources.append({
            "path": str(retrieval_path),
            "sha256": sha256(retrieval_path.read_bytes()).hexdigest(),
            "artifact_identity": str(retrieval["artifact_identity"]),
        })

    partitions: dict[str, str] = {}
    split_source: dict[str, str] | None = None
    if split_manifest_path is not None:
        split_payload = json.loads(split_manifest_path.read_text(encoding="utf-8"))
        if (
            split_payload.get("question_set_identity") != payload.get("question_set_identity")
            or split_payload.get("split_identity") != payload.get("split_identity")
        ):
            raise RAGEvalContractError("rag_m34_history_split_mismatch", str(split_manifest_path))
        partitions.update({str(item): "diagnostic_dev" for item in split_payload["diagnostic_dev_question_ids"]})
        partitions.update({str(item): "held_out" for item in split_payload["held_out_question_ids"]})
        if set(partitions) != set(question_ids):
            raise RAGEvalContractError("rag_m34_history_split_closed_world", "split 未闭合 180 题")
        split_source = {"path": str(split_manifest_path), "sha256": sha256(split_manifest_path.read_bytes()).hexdigest()}

    # 步骤 3：把旧 Answer/Retrieval 证据投影为逐题 funnel。产品层永远 not_observed。====
    cases: list[dict[str, Any]] = []
    for execution in executions:
        question_id = str(execution["question_id"])
        retrieval = retrieval_by_id.get(question_id)
        result = execution.get("result")
        attempt = execution.get("composer_attempt") or {}
        attempt_status = attempt.get("status")
        if retrieval is None:
            retrieval_layer = _layer("not_observed", "未提供该题的冻结 retrieval artifact")
        else:
            coverage = dict((retrieval.get("coverage") or {}).get("20") or {})
            retrieval_layer = _layer(
                "passed" if coverage.get("all_gold") else "failed",
                "按冻结 lexical retrieval @20 判断 all-gold",
                gold_coverage=coverage,
                actual_logical_document_ids=[item["logical_document_id"] for item in retrieval.get("actual_matches") or ()],
            )
        if execution.get("outcome") == "contract_rejected":
            composer_layer = _layer("failed", str(execution.get("internal_reason_code") or "contract_rejected"))
        elif attempt_status not in {None, "succeeded"}:
            composer_layer = _layer("not_observed", f"provider attempt={attempt_status}")
        else:
            composer_layer = _layer("passed", "AnswerFlow 返回可评分结果")
        citation_layer = (
            _layer("not_observed", "回答结果不可用")
            if result is None and composer_layer["status"] == "not_observed"
            else _layer(
                "passed" if execution["document_coverage"]["all_gold"] else "failed",
                "按 gold document multiset 计算 citation coverage",
                gold_coverage=execution["document_coverage"],
                cited_logical_document_ids=execution.get("cited_logical_document_ids") or [],
            )
        )
        answer_layer = (
            _layer("not_observed", "回答结果不可用")
            if result is None and composer_layer["status"] == "not_observed"
            else _layer(
                "passed" if float(execution.get("exact_fact_coverage") or 0.0) == 1.0 else "failed",
                "保守 exact-fact 字符串下限，不等于语义 correctness",
                exact_fact_coverage=float(execution.get("exact_fact_coverage") or 0.0),
                fact_checks=execution.get("fact_checks") or [],
            )
        )
        layers = {
            "product_api_router_harness_trace": _layer("not_observed", "M34 直接调用 AnswerFlow"),
            "retrieval": retrieval_layer,
            "selected": _layer("not_observed", "M34 artifact 未持久化 selected logical IDs"),
            "generation_visible": _layer("not_observed", "M34 artifact 未持久化 generation-visible logical IDs"),
            "composer_support": composer_layer,
            "citation": citation_layer,
            "answer_exact_fact_lower_bound": answer_layer,
        }
        priority = ("retrieval", "composer_support", "citation", "answer_exact_fact_lower_bound")
        primary = next((name for name in priority if layers[name]["status"] == "failed"), "passed")
        if primary == "passed" and any(layers[name]["status"] == "not_observed" for name in priority):
            primary = "not_observed"
        cases.append({
            "question_id": question_id,
            "partition": partitions.get(question_id, "unknown"),
            "question_type": execution["question_type"],
            "source_types": execution["source_types"],
            "document_cardinality": execution["document_cardinality"],
            "expected_document_ids": execution["expected_document_ids"],
            "primary_failure": primary,
            "layers": layers,
            "provider_usage": execution.get("provider_usage_delta") or {},
        })

    return {
        "format": "phase4-rag-m34-historical-view-v2",
        "source": {"path": str(path), "sha256": file_hash, "artifact_identity": payload["artifact_identity"]},
        "retrieval_sources": retrieval_sources,
        "split_source": split_source,
        "runtime_kind": "external-direct-answer-flow",
        "is_product_harness_e2e": False,
        "question_count": len(executions),
        "answer_flow_call_count": sum(int(item.get("answer_flow_calls") or 0) for item in executions),
        "provider_unavailable_count": unavailable,
        "observed_layers": ["retrieval_result", "composer/support", "citation", "exact-fact-string-lower-bound"],
        "not_observed_layers": ["api", "turn", "router", "harness", "selected", "generation-visible", "response-trace-consistency"],
        "summary": overall,
        "group_summaries": _group_summary(cases),
        "cases": cases,
        "boundary": "历史 external 诊断，不能与 M41 business product E2E Gate 或质量分数混算。",
    }


def render_m34_history_report(view: dict[str, Any]) -> str:
    """把大 JSON 的关键 strata 压成可提交 Markdown；逐题证据仍留在 JSON。"""

    lines = [
        "# M34 180题分层历史诊断",
        "",
        f"- questions: `{view['question_count']}`",
        f"- source artifact: `{view['source']['artifact_identity']}`",
        "- product API/Router/Harness: `not_observed`（旧运行直接调用 AnswerFlow）",
        "- selected / generation-visible logical IDs: `not_observed`（旧 artifact 未保存）",
        "",
        "| stratum | questions | primary diagnosis |",
        "|---|---:|---|",
    ]
    for name, summary in view["group_summaries"].items():
        counts = ", ".join(f"{key}={value}" for key, value in summary["primary_failure_counts"].items())
        lines.append(f"| {name} | {summary['question_count']} | {counts} |")
    lines.extend([
        "",
        "## 边界",
        "",
        "- `answer_exact_fact_lower_bound` 是保守字符串下限，不能冒充语义错误率。",
        "- 本报告零 Tool/LLM 调用，只消费冻结的 M34 Answer/Retrieval artifacts。",
        "- 逐题 funnel 见同次生成的 JSON；M41 external 产品运行另行分账。",
        "",
    ])
    return "\n".join(lines)
