"""M41 RAG failure funnel、typed assertion、Gate、triage 与报告投影。"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Callable
import unicodedata

from eval.rag_e2e_contracts import (
    AssertionEffect,
    AssertionStatus,
    RAGAssertionResult,
    RAGExecutionEvidence,
    RAGGate,
    RAGScenario,
    RAG_ASSERTION_IDS,
    RAGEvalContractError,
)


SUPPORTED_ASSERTIONS = RAG_ASSERTION_IDS


def score_execution(
    scenario: RAGScenario, evidence: RAGExecutionEvidence
) -> tuple[RAGAssertionResult, ...]:
    """所有 assertions 只读同一份 execution evidence。"""

    results: list[RAGAssertionResult] = []
    for effect, assertion_ids in (
        ("required", scenario.required_assertions),
        ("advisory", scenario.advisory_assertions),
    ):
        for assertion_id in assertion_ids:
            if assertion_id not in SUPPORTED_ASSERTIONS:
                raise RAGEvalContractError("rag_assertion_unknown", assertion_id)
            status, reason = _evaluate(assertion_id, scenario, evidence)
            results.append(
                RAGAssertionResult(
                    scenario.scenario_id,
                    evidence.replicate,
                    assertion_id,
                    effect,  # type: ignore[arg-type]
                    status,
                    reason,
                    evidence.evidence_ref,
                )
            )
    return tuple(results)


def _evaluate(
    assertion_id: str, scenario: RAGScenario, evidence: RAGExecutionEvidence
) -> tuple[AssertionStatus, str]:
    """集中处理 not_observed；上游失败不会被误算成下游语义错误。"""

    axes = (evidence.route, evidence.execution_status, evidence.answer_status, evidence.safety_status)
    external_unavailable = _external_unavailable(evidence)
    composer_contract_failed = evidence.reason_code in {
        "composer_output_invalid", "composer_evidence_invalid", "composer_budget_invalid",
        "citation_projection_invalid", "composer_unavailable",
    }
    if external_unavailable and assertion_id in {
        "axes_correct", "reason_correct", "cited_gold", "answer_present",
        "required_answer_terms", "forbidden_terms_absent",
        "answer_facts_exact_lower_bound",
    }:
        return "not_observed", "provider 外部不可用，不能判断下游语义结果"
    if composer_contract_failed and assertion_id in {
        "cited_gold", "answer_present", "required_answer_terms", "answer_facts_exact_lower_bound",
    }:
        return "not_observed", "Composer/support 已观察失败，下游答案与引用不可评分"
    simple: dict[str, Callable[[], bool]] = {
        "route_correct": lambda: evidence.route == scenario.expected_axes[0],
        "axes_correct": lambda: axes == scenario.expected_axes,
        "reason_correct": lambda: evidence.reason_code == scenario.expected_reason,
        "graph_path_correct": lambda: evidence.graph_steps == ("route", "rag_tool", "controller"),
        "rag_tool_once": lambda: evidence.graph_invocation_count == 1 and evidence.rag_tool_calls == 1,
        "answer_present": lambda: bool(evidence.answer and evidence.answer.strip()),
        "answer_absent": lambda: not evidence.answer,
        # Harness 会把深 Tool 的空 answer 投影为稳定、安全的公开兜底文本；这不是业务答案，
        # Eval 不能把现有产品合同误判为“凭空生成了保修规则”。
        "safe_fallback_answer": lambda: evidence.answer == "当前无法形成可公开的答案。",
        "no_generation": lambda: int(evidence.rag_diagnostics.get("composer_calls") or 0) == 0
        and not evidence.provider_attempts,
        "response_trace_consistent": lambda: evidence.response_trace_consistent,
        "runtime_identity_complete": lambda: evidence.trace_runtime_identity.get("status") == "complete",
        "provider_observed": lambda: bool(evidence.provider_attempts),
        "composer_support_valid": lambda: not composer_contract_failed and evidence.answer_status == "complete",
        "forbidden_terms_absent": lambda: not any(
            term in ((evidence.answer or "") + str(evidence.citations) + str(evidence.docs_used))
            for term in scenario.forbidden_public_terms
        ),
    }
    if assertion_id in simple:
        passed = simple[assertion_id]()
        return ("passed" if passed else "failed", f"{assertion_id}={passed}")

    if assertion_id == "required_answer_terms":
        if not evidence.answer:
            return "not_observed", "answer 不可用，无法判断 required terms"
        missing = [term for term in scenario.required_answer_terms if term not in evidence.answer]
        return ("failed", f"missing_terms={missing}") if missing else ("passed", "required terms 全部出现")

    if assertion_id == "answer_facts_exact_lower_bound":
        if not evidence.answer:
            return "not_observed", "answer 不可用，无法计算 exact-fact 下限"
        normalized = " ".join(
            "".join(char if char.isalnum() else " " for char in unicodedata.normalize("NFKC", evidence.answer).casefold()).split()
        )
        checks = {
            fact: bool(fact.strip()) and " ".join(
                "".join(char if char.isalnum() else " " for char in unicodedata.normalize("NFKC", fact).casefold()).split()
            ) in normalized
            for fact in scenario.answer_facts
        }
        passed = bool(checks) and all(checks.values())
        return ("passed" if passed else "failed", f"exact_fact_checks={checks}")

    stage_by_assertion = {
        "retrieved_gold": "candidate",
        "selected_gold": "selected",
        "generation_visible_gold": "generation_visible",
        "cited_gold": "cited",
    }
    stage = stage_by_assertion[assertion_id]
    if evidence.identities_redacted:
        return "not_observed", "安全拒绝路径不持久化文档 identity"
    if evidence.execution_status == "external_unavailable":
        return "not_observed", "外部不可用导致该 funnel 层不可观察"
    if composer_contract_failed and not dict(evidence.stage_document_keys).get(stage):
        return "not_observed", "合同拒绝前的该层 logical IDs 未进入安全 Evidence 投影"
    keys = Counter(dict(evidence.stage_document_keys).get(stage, ()))
    expected = Counter(scenario.expected_document_keys)
    passed = all(keys[key] >= count for key, count in expected.items())
    return ("passed" if passed else "failed", f"stage={stage} expected={dict(expected)} actual={dict(keys)}")


def _external_unavailable(evidence: RAGExecutionEvidence) -> bool:
    """只把 transport/配额/出站不可用归为 inconclusive；模型返回坏结构仍是 observed failure。"""

    if not evidence.provider_attempts:
        return False
    subtype = str(evidence.provider_attempts[-1].get("error_subtype") or "")
    return (
        subtype in {"timeout", "network_error", "network_permission_denied", "rate_limited", "account_arrearage", "outbound_denied"}
        or subtype.startswith("http_")
    )


def project_gate(assertions: tuple[RAGAssertionResult, ...]) -> RAGGate:
    """required failed 优先；无 failed 但有 not_observed 时为 inconclusive。"""

    required = [item for item in assertions if item.effect == "required"]
    passed = sum(item.status == "passed" for item in required)
    failed = sum(item.status == "failed" for item in required)
    not_observed = sum(item.status == "not_observed" for item in required)
    status = "failed" if failed else "inconclusive" if not_observed else "passed"
    return RAGGate(status, passed, failed, not_observed)  # type: ignore[arg-type]


def triage_execution(
    scenario: RAGScenario,
    evidence: RAGExecutionEvidence,
    assertions: tuple[RAGAssertionResult, ...],
) -> dict[str, object]:
    """按真实执行顺序给出首个主要失败层，同时保留全部失败 assertion。"""

    failed = [item for item in assertions if item.status == "failed"]
    unobserved = [item for item in assertions if item.status == "not_observed"]
    priority = [
        ("product_runtime", {"route_correct", "axes_correct", "reason_correct", "graph_path_correct", "rag_tool_once", "response_trace_consistent", "runtime_identity_complete"}),
        ("retrieval", {"retrieved_gold"}),
        ("selection", {"selected_gold"}),
        ("generation_context", {"generation_visible_gold"}),
        ("provider_or_support", {"provider_observed", "composer_support_valid", "no_generation"}),
        ("citation", {"cited_gold"}),
        ("answer", {"answer_present", "answer_absent", "safe_fallback_answer", "required_answer_terms", "forbidden_terms_absent"}),
    ]
    primary = "passed"
    for stage, ids in priority:
        if any(item.assertion_id in ids for item in failed):
            primary = stage
            break
    if primary == "passed" and unobserved:
        primary = "not_observed"
    return {
        "scenario_id": scenario.scenario_id,
        "replicate": evidence.replicate,
        "primary_stage": primary,
        "failed_assertions": [item.assertion_id for item in failed],
        "not_observed_assertions": [item.assertion_id for item in unobserved],
        "reason_code": evidence.reason_code,
        "execution_status": evidence.execution_status,
        "provider_attempts": len(evidence.provider_attempts),
        "review_required": bool(failed or unobserved),
    }


def render_report(
    *,
    artifact: dict[str, object],
    scenarios: dict[str, RAGScenario],
    triage: tuple[dict[str, object], ...],
) -> str:
    """把 artifact 投影为可读报告；报告不是第二份事实源。"""

    gate = artifact["gate"]
    assert isinstance(gate, dict)
    lines = [
        "# Phase 4 RAG E2E Eval Report",
        "",
        f"- run_id: `{artifact['run_spec']['run_id']}`",  # type: ignore[index]
        f"- artifact_identity: `{artifact['artifact_identity']}`",
        f"- Gate: **{gate['status']}**",
        f"- required: passed={gate['passed']} / failed={gate['failed']} / not_observed={gate['not_observed']}",
        "",
        "## Failure Funnel",
        "",
        "| scenario | replicate | axes | candidate | selected | generation_visible | cited | primary_triage |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    triage_by_key = {(item["scenario_id"], item["replicate"]): item for item in triage}
    for raw in artifact["executions"]:  # type: ignore[index]
        assert isinstance(raw, dict)
        counts = dict(raw["stage_counts"])
        axes = "/".join(
            str(raw[key]) for key in ("route", "execution_status", "answer_status", "safety_status")
        )
        item = triage_by_key[(raw["scenario_id"], raw["replicate"])]
        lines.append(
            f"| {raw['scenario_id']} | {raw['replicate']} | {axes} | {counts.get('candidate', 0)} | "
            f"{counts.get('selected', 0)} | {counts.get('generation_visible', 0)} | "
            f"{counts.get('cited', 0)} | {item['primary_stage']} |"
        )
    lines.extend(["", "## Assertion Views", "", "| kind | eligible | passed | failed | not_observed |", "|---|---:|---:|---:|---:|"])
    for effect in ("required", "advisory"):
        selected = [item for item in artifact["assertions"] if item["effect"] == effect]  # type: ignore[index]
        counts = Counter(item["status"] for item in selected)
        lines.append(
            f"| {effect} | {len(selected)} | {counts['passed']} | {counts['failed']} | {counts['not_observed']} |"
        )
    # ★ catalog 可以是 canonical 180，而本次只跑其中一个 suite；报告必须严格按
    # RunSpec 选中题统计，不能把未运行题的数量混进本次分母。
    selected_ids = tuple(artifact["run_spec"]["selected_scenario_ids"])  # type: ignore[index]
    external = [scenarios[scenario_id] for scenario_id in selected_ids if scenarios[scenario_id].question_type != "business"]
    if external:
        lines.extend([
            "", "## External Strata Outcomes", "",
            "| stratum | executions | primary diagnosis | required p/f/n | retrieved/selected/visible/cited gold |",
            "|---|---:|---|---|---|",
        ])
        scenario_groups: dict[str, set[str]] = {}
        for item in external:
            names = (
                f"difficulty:{item.difficulty}",
                f"partition:{item.classification}",
                f"type:{item.question_type}",
                f"cardinality:{item.document_cardinality}",
                f"source:{'+'.join(item.source_types)}",
            )
            for name in names:
                scenario_groups.setdefault(name, set()).add(item.scenario_id)
        artifact_assertions = artifact["assertions"]  # type: ignore[index]
        artifact_executions = artifact["executions"]  # type: ignore[index]
        funnel_ids = ("retrieved_gold", "selected_gold", "generation_visible_gold", "cited_gold")
        for name, group_ids in sorted(scenario_groups.items()):
            grouped_triage = [item for item in triage if item["scenario_id"] in group_ids]
            primary = Counter(str(item["primary_stage"]) for item in grouped_triage)
            required = [
                item for item in artifact_assertions
                if item["scenario_id"] in group_ids and item["effect"] == "required"
            ]
            status = Counter(str(item["status"]) for item in required)
            funnel = {
                assertion_id: sum(
                    item["scenario_id"] in group_ids
                    and item["assertion_id"] == assertion_id
                    and item["status"] == "passed"
                    for item in artifact_assertions
                )
                for assertion_id in funnel_ids
            }
            execution_count = sum(item["scenario_id"] in group_ids for item in artifact_executions)
            primary_text = ", ".join(f"{key}={value}" for key, value in sorted(primary.items()))
            funnel_text = "/".join(str(funnel[key]) for key in funnel_ids)
            lines.append(
                f"| {name} | {execution_count} | {primary_text} | "
                f"{status['passed']}/{status['failed']}/{status['not_observed']} | {funnel_text} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "- 本报告来自每题一次真实产品链路执行；scorer/report/review 没有重跑 retrieval 或 LLM。",
            "- retrieval、citation 或 `answer_status=complete` 均不单独等于自然语言答案正确。",
            "- provider unavailable 进入 `not_observed`，不能伪装成 semantic wrong。",
            "- deterministic M31–M40 Gate、M34 external benchmark 与本 RAG E2E 结果分账。",
        ]
    )
    return "\n".join(lines) + "\n"
