"""M46-E：Agent Scenario v4 的 parent/child 同源 artifact。

v3 只记录父级 Decision Loop；v4 在不改变旧 artifact 的前提下，额外验证一次 Knowledge
父动作内部的 B4 child timeline。API、Trace 和 Eval 都必须复制同一个 ``ActionAttempt`` 安全
投影，Eval 不得根据日志文字重新猜 action 或补算预算。
"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.b4_contracts import B4ContractBundle
from engine.phase4b.identity import canonical_hash
from engine.phase4b.scenario_projection import agent_scenario_source_identity

ARTIFACT_VERSION = "phase4b-agent-scenario-artifact-v4"
ASSERTION_STATUSES = {"passed", "failed", "not_observed"}
STRATEGIES = {"pipeline", "subgraph"}
PARENT_ACTIONS = {"collect_sql_evidence", "collect_document_evidence", "repair_sql_evidence"}
RUN_SPEC_FIELDS = {
    "run_id", "contract_identity", "seed_identity", "caller_identity",
    "knowledge_runtime_identities", "policy_identities", "strategy",
}
TURN_FIELDS = {
    "scenario_id", "turn_id", "task_delta", "task_state", "actions", "budget",
    "node_contexts", "termination", "runtime_identity", "assertions",
    "source_projection_identity",
}
ACTION_FIELDS = {
    "ordinal", "action_id", "requirement_identity", "input_fingerprint", "duplicate_key",
    "status", "observation", "budget_before", "consumed", "budget_after",
    "evidence_delta", "progress",
}
OBSERVATION_FIELDS = {
    "tool_name", "route", "execution_status", "answer_status", "safety_status",
    "reason_code", "error_type", "evidence_refs", "diagnostics",
}
CHILD_FIELDS = {
    "attempts", "consumption", "termination", "detail_code", "admission_decision",
    "admission_reason_code", "formed_requirements",
}
CHILD_ATTEMPT_FIELDS = {
    "ordinal", "action", "status", "eligible_actions", "rejected_actions",
    "evidence_added", "duplicate_count", "consumption", "progress_reason",
}
CHILD_CONSUMPTION_FIELDS = {
    "initial_retrieval_batches", "rewrite_retrieval_batches", "expansion_candidates_scanned",
    "expansion_evidence_added", "candidates_examined", "unique_merged_evidence", "selected",
    "generation_visible", "proposal_calls", "model_calls", "total_tokens",
    "token_usage_observed", "retrieval_attempts_observed", "latency_ms",
}


def _source_identity(turn: Mapping[str, Any]) -> str:
    return agent_scenario_source_identity(
        actions=turn["actions"],
        budget=turn["budget"],
        termination=turn["termination"],
        runtime_identity=turn["runtime_identity"],
    )


def project_task_turn_v4(
    *,
    task_turn: Any,
    scenario_id: str,
    turn_id: str,
    assertions: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    """从唯一 TaskTurnResult 复制安全投影，并固化可与 API/Trace 对账的 hash。"""

    if task_turn.agent_loop is None or task_turn.delta is None or task_turn.task is None:
        raise ValueError("agent_scenario_v4_source_incomplete")
    loop = task_turn.agent_loop
    turn = {
        "scenario_id": scenario_id,
        "turn_id": turn_id,
        "task_delta": task_turn.delta.safe_projection(),
        "task_state": task_turn.task.state.safe_projection(),
        "actions": [item.safe_projection() for item in loop.attempts],
        "budget": loop.budget.safe_projection(),
        "node_contexts": [item.safe_projection() for item in task_turn.node_contexts],
        "termination": loop.termination.safe_projection(),
        "runtime_identity": dict(loop.runtime_identity),
        "assertions": [[identity, status] for identity, status in assertions],
    }
    return {**turn, "source_projection_identity": _source_identity(turn)}


def build_agent_scenario_v4(
    *, bundle: B4ContractBundle, run_spec: Mapping[str, Any], turns: tuple[Mapping[str, Any], ...]
) -> dict[str, Any]:
    """建立 completed v4 artifact；不运行 Tool，也不修改 source projection。"""

    normalized_spec = dict(run_spec)
    normalized_spec["contract_identity"] = bundle.content_identity
    unsigned = {
        "artifact_version": ARTIFACT_VERSION,
        "status": "completed",
        "run_spec": normalized_spec,
        "run_spec_identity": canonical_hash(normalized_spec),
        "turns": [dict(item) for item in turns],
    }
    artifact = {**unsigned, "artifact_identity": canonical_hash(unsigned)}
    validate_agent_scenario_v4(artifact, bundle=bundle)
    return artifact


def validate_agent_scenario_v4(payload: Mapping[str, Any], *, bundle: B4ContractBundle) -> None:
    """拒绝 shape/identity/父子预算/私有字段漂移。"""

    if set(payload) != {
        "artifact_version", "status", "run_spec", "run_spec_identity", "turns", "artifact_identity"
    }:
        raise ValueError("agent_scenario_v4_shape_invalid")
    if payload["artifact_version"] != ARTIFACT_VERSION or payload["status"] != "completed":
        raise ValueError("agent_scenario_v4_version_invalid")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise ValueError("agent_scenario_v4_identity_mismatch")
    run_spec = payload["run_spec"]
    if not isinstance(run_spec, dict) or set(run_spec) != RUN_SPEC_FIELDS:
        raise ValueError("agent_scenario_v4_run_spec_invalid")
    if run_spec["strategy"] not in STRATEGIES or run_spec["contract_identity"] != bundle.content_identity:
        raise ValueError("agent_scenario_v4_run_spec_invalid")
    if payload["run_spec_identity"] != canonical_hash(run_spec):
        raise ValueError("agent_scenario_v4_run_spec_identity_mismatch")
    turns = payload["turns"]
    if not isinstance(turns, list) or not turns:
        raise ValueError("agent_scenario_v4_turns_invalid")
    seen: set[tuple[str, str]] = set()
    for turn in turns:
        _validate_turn(turn, strategy=run_spec["strategy"], bundle=bundle)
        key = (str(turn["scenario_id"]), str(turn["turn_id"]))
        if key in seen:
            raise ValueError("agent_scenario_v4_turn_duplicate")
        seen.add(key)
    _reject_private_payload(payload)


def _validate_turn(
    turn: Mapping[str, Any], *, strategy: str, bundle: B4ContractBundle
) -> None:
    if set(turn) != TURN_FIELDS or turn["scenario_id"] not in bundle.payload["scenarios"]:
        raise ValueError("agent_scenario_v4_turn_invalid")
    if turn["source_projection_identity"] != _source_identity(turn):
        raise ValueError("agent_scenario_v4_source_identity_mismatch")
    actions = turn["actions"]
    if not isinstance(actions, list) or len(actions) > int(bundle.payload["parent_budget"]["max_actions"]):
        raise ValueError("agent_scenario_v4_actions_invalid")
    prior_after: Mapping[str, Any] | None = None
    child_count = 0
    for ordinal, action in enumerate(actions, 1):
        if set(action) != ACTION_FIELDS or action["ordinal"] != ordinal or action["action_id"] not in PARENT_ACTIONS:
            raise ValueError("agent_scenario_v4_action_invalid")
        if set(action["observation"]) != OBSERVATION_FIELDS:
            raise ValueError("agent_scenario_v4_observation_invalid")
        if prior_after is not None and action["budget_before"] != prior_after:
            raise ValueError("agent_scenario_v4_budget_chain_invalid")
        _validate_budget_step(action)
        prior_after = action["budget_after"]
        diagnostics = action["observation"]["diagnostics"]
        child = diagnostics.get("b4_subgraph") if isinstance(diagnostics, dict) else None
        if child is not None:
            child_count += 1
            _validate_child(child, bundle=bundle)
    if actions and turn["budget"] != actions[-1]["budget_after"]:
        raise ValueError("agent_scenario_v4_budget_final_mismatch")
    if strategy == "subgraph" and child_count != 1:
        raise ValueError("agent_scenario_v4_child_projection_missing")
    if strategy == "pipeline" and child_count:
        raise ValueError("agent_scenario_v4_pipeline_child_invalid")
    assertions = turn["assertions"]
    if not isinstance(assertions, list) or len({item[0] for item in assertions}) != len(assertions):
        raise ValueError("agent_scenario_v4_assertions_invalid")
    if any(not isinstance(item, list) or len(item) != 2 or item[1] not in ASSERTION_STATUSES for item in assertions):
        raise ValueError("agent_scenario_v4_assertions_invalid")


def _validate_child(child: Mapping[str, Any], *, bundle: B4ContractBundle) -> None:
    if set(child) != CHILD_FIELDS or child["termination"] not in bundle.payload["terminations"]:
        raise ValueError("agent_scenario_v4_child_invalid")
    consumption = child["consumption"]
    if set(consumption) != CHILD_CONSUMPTION_FIELDS:
        raise ValueError("agent_scenario_v4_child_consumption_invalid")
    limits = bundle.payload["child_budget"]
    if (
        consumption["initial_retrieval_batches"] > limits["max_initial_retrieval_batches"]
        or consumption["rewrite_retrieval_batches"] > limits["max_rewrite_retrieval_batches"]
        or consumption["candidates_examined"] > limits["max_total_candidates"]
        or consumption["selected"] > limits["max_selected"]
        or consumption["generation_visible"] > limits["max_generation_visible"]
        or consumption["proposal_calls"] > limits["max_proposal_calls"]
        or consumption["model_calls"] > limits["max_model_calls"]
    ):
        raise ValueError("agent_scenario_v4_child_budget_invalid")
    attempts = child["attempts"]
    if not isinstance(attempts, list) or len(attempts) > limits["max_recovery_actions"]:
        raise ValueError("agent_scenario_v4_child_attempts_invalid")
    for ordinal, attempt in enumerate(attempts, 1):
        if set(attempt) != CHILD_ATTEMPT_FIELDS or attempt["ordinal"] != ordinal:
            raise ValueError("agent_scenario_v4_child_attempt_invalid")
        if attempt["action"] not in bundle.payload["actions"] or set(attempt["consumption"]) != CHILD_CONSUMPTION_FIELDS:
            raise ValueError("agent_scenario_v4_child_attempt_invalid")


def _validate_budget_step(action: Mapping[str, Any]) -> None:
    before, consumed, after = action["budget_before"], action["consumed"], action["budget_after"]
    if set(before) != {"profile", "consumed"} or set(after) != {"profile", "consumed"}:
        raise ValueError("agent_scenario_v4_budget_shape_invalid")
    if before["profile"] != after["profile"] or set(consumed) != set(before["consumed"]) or set(consumed) != set(after["consumed"]):
        raise ValueError("agent_scenario_v4_budget_shape_invalid")
    for key, value in consumed.items():
        if key == "token_usage_observed":
            expected = bool(before["consumed"][key]) and bool(value)
        elif key == "latency_ms":
            expected = round(float(before["consumed"][key]) + float(value), 3)
        else:
            expected = int(before["consumed"][key]) + int(value)
        if after["consumed"][key] != expected:
            raise ValueError("agent_scenario_v4_budget_conservation_failed")


def _reject_private_payload(value: Any, *, key: str = "") -> None:
    # Task state 的既有安全投影允许保存用户问题；v4 新增的 child ledger 则由严格字段集合
    # 保证没有 question。这里拦截的是正文、provider 原文和执行私密数据，不能误伤旧合同。
    denied = {"rows", "content", "prompt", "raw_response", "api_key", "thought", "stack"}
    if key.casefold() in denied:
        raise ValueError("agent_scenario_v4_private_payload")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _reject_private_payload(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _reject_private_payload(child)
