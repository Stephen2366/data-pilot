"""M43-F：Agent Scenario artifact v2 的 typed task facts。

M42 v1 保持不可变；v2 只新增 TaskDelta/State transition/Evidence validity/context/lifecycle。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from engine.phase4b.b1_contracts import B1ContractBundle
from engine.phase4b.identity import canonical_hash

ARTIFACT_VERSION = "phase4b-agent-scenario-artifact-v2"
_DELTA_CATEGORIES = {"start_task", "continue", "modify_constraint", "ask_about_existing_result", "add_evidence_requirement", "switch_task", "correct_previous_understanding", "cancel"}
_TRANSITION_FIELDS = {"category", "before_identity", "after_identity", "changed_fields", "invalidated_evidence_count"}
_EVIDENCE_FIELDS = {"ref", "route", "requirement_identity", "validity", "invalidation_reason", "source_generation"}
_CONTEXT_FIELDS = {"purpose", "source_identities", "payload", "field_budget", "input_fingerprint"}
_LIFECYCLE_FIELDS = {"task_safe_ref", "action", "reason_code", "version_before", "version_after", "state_identity", "previous_task_safe_ref"}


@dataclass(frozen=True)
class AgentTaskTurnFact:
    """单个 task turn 的安全事实；所有字段都能从 runtime/Trace 同源投影。"""
    scenario_id: str
    turn_id: str
    delta_category: str
    state_transition: Mapping[str, Any]
    evidence_validity: tuple[Mapping[str, Any], ...]
    node_contexts: tuple[Mapping[str, Any], ...]
    task_lifecycle: Mapping[str, Any]
    graph_invocation_count: int
    task_runtime_invocation_count: int

    def safe_projection(self) -> dict[str, Any]:
        return {"scenario_id": self.scenario_id, "turn_id": self.turn_id, "delta_category": self.delta_category, "state_transition": dict(self.state_transition), "evidence_validity": [dict(item) for item in self.evidence_validity], "node_contexts": [dict(item) for item in self.node_contexts], "task_lifecycle": dict(self.task_lifecycle), "graph_invocation_count": self.graph_invocation_count, "task_runtime_invocation_count": self.task_runtime_invocation_count}


def build_agent_scenario_v2(*, bundle: B1ContractBundle, turns: tuple[AgentTaskTurnFact, ...]) -> dict[str, Any]:
    """构造可对账 artifact；正文/rows/raw task id 不在允许字段中。"""

    payload = {"artifact_version": ARTIFACT_VERSION, "contract_identity": bundle.content_identity, "turns": [item.safe_projection() for item in turns]}
    payload["content_identity"] = canonical_hash(payload)
    validate_agent_scenario_v2(payload)
    return payload


def validate_agent_scenario_v2(payload: Mapping[str, Any]) -> None:
    """closed-world 验证 v2，拒绝借未知字段塞入历史正文或执行结果。"""

    if set(payload) != {"artifact_version", "contract_identity", "turns", "content_identity"}:
        raise ValueError("agent_scenario_v2_shape_invalid")
    if payload["artifact_version"] != ARTIFACT_VERSION:
        raise ValueError("agent_scenario_v2_version_invalid")
    unhashed = {key: value for key, value in payload.items() if key != "content_identity"}
    if payload["content_identity"] != canonical_hash(unhashed):
        raise ValueError("agent_scenario_v2_identity_mismatch")
    expected = {"scenario_id", "turn_id", "delta_category", "state_transition", "evidence_validity", "node_contexts", "task_lifecycle", "graph_invocation_count", "task_runtime_invocation_count"}
    for turn in payload["turns"]:
        if set(turn) != expected or turn["graph_invocation_count"] not in {0, 1} or turn["task_runtime_invocation_count"] not in {0, 1}:
            raise ValueError("agent_scenario_v2_turn_invalid")
        if turn["delta_category"] not in _DELTA_CATEGORIES or set(turn["state_transition"]) != _TRANSITION_FIELDS:
            raise ValueError("agent_scenario_v2_transition_invalid")
        if any(set(item) != _EVIDENCE_FIELDS for item in turn["evidence_validity"]):
            raise ValueError("agent_scenario_v2_evidence_invalid")
        if any(set(item) != _CONTEXT_FIELDS for item in turn["node_contexts"]):
            raise ValueError("agent_scenario_v2_context_invalid")
        if set(turn["task_lifecycle"]) != _LIFECYCLE_FIELDS:
            raise ValueError("agent_scenario_v2_lifecycle_invalid")
        serialized = str(turn).lower()
        if any(token in serialized for token in ("document_body", "raw_task_id")):
            raise ValueError("agent_scenario_v2_private_payload")
