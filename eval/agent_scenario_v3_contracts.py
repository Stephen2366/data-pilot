"""M44-F：Agent Scenario v3 的 closed-world Decision Loop artifact。"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.b2_contracts import B2ContractBundle
from engine.phase4b.identity import canonical_hash

ARTIFACT_VERSION = "phase4b-agent-scenario-artifact-v3"
ASSERTION_STATUSES = {"passed", "failed", "not_observed"}
RUN_SPEC_FIELDS = {
    "run_id", "contract_identity", "seed_identity", "caller_identity",
    "knowledge_runtime_identities", "policy_identities",
}
TURN_FIELDS = {
    "scenario_id", "turn_id", "task_delta", "task_state", "actions", "budget",
    "node_contexts", "termination", "runtime_identity", "assertions",
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
DELTA_FIELDS = {"added", "removed", "invalidated", "duplicate"}
PROGRESS_FIELDS = {"coverage_increased", "eligible_action_remains", "reason_code"}
TERMINATION_FIELDS = {
    "reason", "detail_code", "active_requirement_identities", "unresolved_requirement_identities",
}
CONTEXT_FIELDS = {
    "context_version", "purpose", "source_identities", "payload", "allowed_fields",
    "field_budget", "token_budget", "estimated_tokens", "input_fingerprint",
}


def build_agent_scenario_v3(
    *, bundle: B2ContractBundle, run_spec: Mapping[str, Any], turns: tuple[Mapping[str, Any], ...]
) -> dict[str, Any]:
    """从 TaskTurnResult/AgentLoopResult 的安全投影构造一次 completed artifact。"""

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
    validate_agent_scenario_v3(artifact, bundle=bundle)
    return artifact


def project_task_turn_v3(
    *, task_turn: Any, scenario_id: str, turn_id: str,
    assertions: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    """从唯一 TaskTurnResult 取事实；Eval 侧不得重跑 Tool 或重新推断 action。"""

    if task_turn.agent_loop is None or task_turn.delta is None or task_turn.task is None:
        raise ValueError("agent_scenario_v3_source_incomplete")
    loop = task_turn.agent_loop
    return {
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


def validate_agent_scenario_v3(payload: Mapping[str, Any], *, bundle: B2ContractBundle) -> None:
    """拒绝形状漂移、动作/预算不守恒、私有 payload 和 identity 篡改。"""

    if set(payload) != {
        "artifact_version", "status", "run_spec", "run_spec_identity", "turns", "artifact_identity"
    }:
        raise ValueError("agent_scenario_v3_shape_invalid")
    if payload["artifact_version"] != ARTIFACT_VERSION or payload["status"] != "completed":
        raise ValueError("agent_scenario_v3_version_invalid")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise ValueError("agent_scenario_v3_identity_mismatch")
    run_spec = payload["run_spec"]
    if not isinstance(run_spec, dict) or set(run_spec) != RUN_SPEC_FIELDS:
        raise ValueError("agent_scenario_v3_run_spec_invalid")
    if payload["run_spec_identity"] != canonical_hash(run_spec):
        raise ValueError("agent_scenario_v3_run_spec_identity_mismatch")
    if run_spec["contract_identity"] != bundle.content_identity:
        raise ValueError("agent_scenario_v3_contract_identity_mismatch")
    if not all(str(run_spec[key]).strip() for key in ("run_id", "seed_identity", "caller_identity")):
        raise ValueError("agent_scenario_v3_run_spec_invalid")
    if not isinstance(payload["turns"], list) or not payload["turns"]:
        raise ValueError("agent_scenario_v3_turns_invalid")
    turn_keys: set[tuple[str, str]] = set()
    for turn in payload["turns"]:
        _validate_turn(turn, bundle=bundle)
        key = (str(turn["scenario_id"]), str(turn["turn_id"]))
        if key in turn_keys:
            raise ValueError("agent_scenario_v3_turn_duplicate")
        turn_keys.add(key)
    _reject_private_payload(payload)


def _validate_turn(turn: Mapping[str, Any], *, bundle: B2ContractBundle) -> None:
    if set(turn) != TURN_FIELDS or turn["scenario_id"] not in bundle.payload["scenarios"]:
        raise ValueError("agent_scenario_v3_turn_invalid")
    actions = turn["actions"]
    if not isinstance(actions, list) or len(actions) > bundle.payload["budget_profile"]["max_actions"]:
        raise ValueError("agent_scenario_v3_actions_invalid")
    duplicate_keys: set[str] = set()
    previous_after: Mapping[str, Any] | None = None
    for expected_ordinal, action in enumerate(actions, 1):
        if set(action) != ACTION_FIELDS or action["ordinal"] != expected_ordinal:
            raise ValueError("agent_scenario_v3_action_shape_invalid")
        if action["action_id"] not in bundle.payload["actions"]:
            raise ValueError("agent_scenario_v3_action_unknown")
        if action["duplicate_key"] in duplicate_keys:
            raise ValueError("agent_scenario_v3_action_duplicate")
        duplicate_keys.add(action["duplicate_key"])
        if set(action["observation"]) != OBSERVATION_FIELDS:
            raise ValueError("agent_scenario_v3_observation_invalid")
        if set(action["evidence_delta"]) != DELTA_FIELDS or set(action["progress"]) != PROGRESS_FIELDS:
            raise ValueError("agent_scenario_v3_progress_invalid")
        observation_ids = {
            str(item.get("evidence_id")) for item in action["observation"]["evidence_refs"]
            if isinstance(item, dict)
        }
        delta_ids = {
            str(item.get("evidence_id")) for field in ("added", "duplicate")
            for item in action["evidence_delta"][field] if isinstance(item, dict)
        }
        if not delta_ids <= observation_ids:
            raise ValueError("agent_scenario_v3_evidence_delta_mismatch")
        if previous_after is not None and action["budget_before"] != previous_after:
            raise ValueError("agent_scenario_v3_budget_chain_invalid")
        _validate_budget_step(action)
        previous_after = action["budget_after"]
    if set(turn["termination"]) != TERMINATION_FIELDS:
        raise ValueError("agent_scenario_v3_termination_invalid")
    if turn["termination"]["reason"] not in bundle.payload["terminations"]:
        raise ValueError("agent_scenario_v3_termination_invalid")
    if actions and turn["budget"] != actions[-1]["budget_after"]:
        raise ValueError("agent_scenario_v3_budget_final_mismatch")
    for context in turn["node_contexts"]:
        _validate_context(context)
    assertions = turn["assertions"]
    if not isinstance(assertions, list) or any(
        not isinstance(item, list) or len(item) != 2 for item in assertions
    ):
        raise ValueError("agent_scenario_v3_assertions_invalid")
    if len({item[0] for item in assertions}) != len(assertions) or any(
        item[1] not in ASSERTION_STATUSES for item in assertions
    ):
        raise ValueError("agent_scenario_v3_assertions_invalid")


def _validate_context(context: Mapping[str, Any]) -> None:
    if set(context) != CONTEXT_FIELDS or context["context_version"] != "phase4b-agent-node-context-v2":
        raise ValueError("agent_scenario_v3_context_invalid")
    payload = context["payload"]
    if not isinstance(payload, dict) or set(payload) - set(context["allowed_fields"]):
        raise ValueError("agent_scenario_v3_context_invalid")
    if len(payload) > context["field_budget"]:
        raise ValueError("agent_scenario_v3_context_budget_invalid")
    estimated = max(1, (len(str(payload)) + 3) // 4)
    if estimated != context["estimated_tokens"] or estimated > context["token_budget"]:
        raise ValueError("agent_scenario_v3_context_budget_invalid")
    identity = canonical_hash({
        "context_version": context["context_version"], "purpose": context["purpose"],
        "source_identities": tuple(context["source_identities"]), "payload": payload,
        "allowed_fields": tuple(context["allowed_fields"]), "field_budget": context["field_budget"],
        "token_budget": context["token_budget"],
    })
    if identity != context["input_fingerprint"]:
        raise ValueError("agent_scenario_v3_context_identity_mismatch")


def _validate_budget_step(action: Mapping[str, Any]) -> None:
    before = action["budget_before"]
    after = action["budget_after"]
    if set(before) != {"profile", "consumed"} or set(after) != {"profile", "consumed"}:
        raise ValueError("agent_scenario_v3_budget_shape_invalid")
    if before["profile"] != after["profile"]:
        raise ValueError("agent_scenario_v3_budget_profile_drift")
    consumed = action["consumed"]
    if set(consumed) != set(before["consumed"]) or set(consumed) != set(after["consumed"]):
        raise ValueError("agent_scenario_v3_budget_shape_invalid")
    for key, value in consumed.items():
        if key == "token_usage_observed":
            expected = bool(before["consumed"][key]) and bool(value)
        elif key == "latency_ms":
            expected = round(float(before["consumed"][key]) + float(value), 3)
        else:
            expected = int(before["consumed"][key]) + int(value)
        if after["consumed"][key] != expected:
            raise ValueError("agent_scenario_v3_budget_conservation_failed")


def _reject_private_payload(value: Any, *, key: str = "") -> None:
    denied_keys = {"rows", "content", "prompt", "raw_task_id", "stack", "technical_message", "api_key", "thought"}
    if key.lower() in denied_keys:
        raise ValueError("agent_scenario_v3_private_payload")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _reject_private_payload(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _reject_private_payload(child)
