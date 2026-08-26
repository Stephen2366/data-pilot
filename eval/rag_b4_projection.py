"""M46 专属的 RAG Eval child-ledger 与 provider usage 安全投影。

M41 的 ``RAGExecutionEvidence`` 已经是历史 closed-world artifact。B4 不在它的顶层追加
字段，而是只对明确的 ``phase4b-b4`` runtime，把 acquisition 事实放入已有的
``rag_diagnostics`` 容器。这样旧运行逐字保持原形，新运行又能审计父动作内部发生了什么。
"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.identity import canonical_hash


B4_RUNTIME_PREFIX = "phase4b-b4-"


def _integer(value: Any) -> int:
    """bool 也是 int 的子类；账本不允许它偷偷充当次数。"""

    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _safe_child_projection(raw: Any) -> dict[str, Any] | None:
    """重新按闭集复制 child ledger，避免 Eval 把未来新增的私有字段顺手落盘。"""

    if not isinstance(raw, Mapping):
        return None
    consumption_raw = raw.get("consumption")
    if not isinstance(consumption_raw, Mapping):
        return None
    numeric_consumption = (
        "initial_retrieval_batches",
        "rewrite_retrieval_batches",
        "expansion_candidates_scanned",
        "expansion_evidence_added",
        "candidates_examined",
        "unique_merged_evidence",
        "selected",
        "generation_visible",
        "proposal_calls",
        "model_calls",
        "total_tokens",
    )
    def safe_consumption(value: Mapping[str, Any]) -> dict[str, Any]:
        projected: dict[str, Any] = {
            key: _integer(value.get(key)) for key in numeric_consumption
        }
        projected.update({
            "token_usage_observed": value.get("token_usage_observed") is True,
            "retrieval_attempts_observed": value.get("retrieval_attempts_observed") is True,
            "latency_ms": float(value.get("latency_ms") or 0.0),
        })
        return projected

    consumption = safe_consumption(consumption_raw)

    attempts: list[dict[str, Any]] = []
    for item in raw.get("attempts") or ():
        if not isinstance(item, Mapping):
            continue
        attempt_consumption = item.get("consumption")
        attempts.append({
            "ordinal": _integer(item.get("ordinal")),
            "action": str(item.get("action") or "stop"),
            "status": str(item.get("status") or "not_observed"),
            "eligible_actions": [str(value) for value in item.get("eligible_actions") or ()],
            "rejected_actions": [str(value) for value in item.get("rejected_actions") or ()],
            "evidence_added": _integer(item.get("evidence_added")),
            "duplicate_count": _integer(item.get("duplicate_count")),
            "consumption": safe_consumption(attempt_consumption)
            if isinstance(attempt_consumption, Mapping) else {},
            "progress_reason": str(item.get("progress_reason") or "not_observed"),
        })

    requirements: list[dict[str, Any]] = []
    requirement_keys = (
        "slot_signature",
        "focused_query_fingerprint",
        "support_group_count",
        "supplier_identity",
        "formation_reason_category",
        "allowed_recovery_actions",
        "coverage_semantics",
    )
    for item in raw.get("formed_requirements") or ():
        if isinstance(item, Mapping):
            requirements.append({key: item[key] for key in requirement_keys if key in item})

    return {
        "attempts": attempts,
        "consumption": consumption,
        "termination": str(raw.get("termination") or "not_observed"),
        "detail_code": str(raw.get("detail_code") or "not_observed"),
        "admission_decision": str(raw.get("admission_decision") or "not_observed"),
        "admission_reason_code": str(raw.get("admission_reason_code") or "not_observed"),
        "formed_requirements": requirements,
    }


def project_b4_eval_diagnostics(
    *,
    runtime_family: str,
    rag_diagnostics: Mapping[str, Any],
    result_evidence_validity: Mapping[str, Any] | None,
    trace_evidence_validity: Mapping[str, Any] | None,
    composer_usage: Mapping[str, int],
) -> tuple[dict[str, Any], dict[str, int]]:
    """投影一次 B4 execution；返回增强 diagnostics 与分项 provider usage。

    ``known`` 很重要：embedding provider 不返回 token usage，所以这里报告可观测下限，
    不把聊天 token 伪装成覆盖所有 provider 的精确总 token。
    """

    diagnostics = dict(rag_diagnostics)
    usage = {str(key): int(value) for key, value in composer_usage.items()}
    if not runtime_family.startswith(B4_RUNTIME_PREFIX):
        return diagnostics, usage

    strategy = "subgraph" if ":subgraph:" in runtime_family else "pipeline"
    result_child = _safe_child_projection((result_evidence_validity or {}).get("subgraph"))
    trace_child = _safe_child_projection((trace_evidence_validity or {}).get("subgraph"))
    if strategy == "pipeline":
        source_consistent = True
    else:
        # Subgraph 的“同源”必须由 result 与 JSONL Trace 两侧同时出现来证明；只看到一侧
        # 是 not_observed，不得因为“没有冲突”就冒充一致。
        source_consistent = (
            result_child is not None
            and trace_child is not None
            and canonical_hash(result_child) == canonical_hash(trace_child)
        )
    child = result_child or trace_child

    composer_requests = _integer(usage.get("request_count", usage.get("requests", 0)))
    composer_tokens = _integer(usage.get("total_tokens", 0))
    if child is not None:
        child_consumption = child["consumption"]
        formation_requests = _integer(child_consumption.get("proposal_calls"))
        formation_tokens = _integer(child_consumption.get("total_tokens"))
        retrieval_requests = (
            _integer(child_consumption.get("initial_retrieval_batches"))
            + _integer(child_consumption.get("rewrite_retrieval_batches"))
        )
        retrieval_observed = child_consumption.get("retrieval_attempts_observed") is True
        formation_tokens_observed = child_consumption.get("token_usage_observed") is True
        projection_status = "observed" if source_consistent else "partial_observed"
    elif strategy == "pipeline":
        formation_requests = formation_tokens = 0
        retrieval_requests = _integer(diagnostics.get("knowledge_tool_calls"))
        retrieval_observed = True
        formation_tokens_observed = True
        projection_status = "not_applicable"
    else:
        formation_requests = formation_tokens = retrieval_requests = 0
        retrieval_observed = False
        formation_tokens_observed = False
        projection_status = "not_observed"

    b4_usage = {
        "composer_requests": composer_requests,
        "composer_total_tokens": composer_tokens,
        "formation_requests": formation_requests,
        "formation_total_tokens": formation_tokens,
        "retrieval_requests_known": retrieval_requests,
        "provider_requests_known_total": composer_requests + formation_requests + retrieval_requests,
        "provider_tokens_known_total": composer_tokens + formation_tokens,
        "retrieval_attempts_observed": retrieval_observed,
        "formation_token_usage_observed": formation_tokens_observed,
        # embedding token usage不可得，所以即使 chat 两侧完整，也只能称 known total。
        "all_provider_token_usage_observed": False,
    }
    diagnostics["b4_acquisition"] = {
        "schema_version": "phase4b-b4-rag-eval-projection-v1",
        "strategy": strategy,
        "projection_status": projection_status,
        "source_consistent": source_consistent,
        "child_ledger": child,
        "provider_usage": b4_usage,
    }
    # 顶层 provider_usage 仍保留 M41 原键；这些 B4 前缀键供通用 compare 分项累计。
    usage.update({
        "b4_composer_requests": composer_requests,
        "b4_composer_total_tokens": composer_tokens,
        "b4_formation_requests": formation_requests,
        "b4_formation_total_tokens": formation_tokens,
        "b4_retrieval_requests_known": retrieval_requests,
        "b4_provider_requests_known_total": b4_usage["provider_requests_known_total"],
        "b4_provider_tokens_known_total": b4_usage["provider_tokens_known_total"],
        "b4_retrieval_attempts_observed": int(retrieval_observed),
        "b4_projection_observed": int(projection_status != "not_observed"),
    })
    return diagnostics, usage
