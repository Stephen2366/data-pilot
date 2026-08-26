"""M46-E：v4 artifact 与 API/Trace 复用同一 B4 parent/child 安全投影。"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from engine.phase4b.b4_contracts import load_b4_contract_bundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_v4_contracts import (
    build_agent_scenario_v4,
    validate_agent_scenario_v4,
)
from tests.test_m46_b4_runtime import _client


def _artifact_from_product_projection(tmp_path: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    trace_path = tmp_path / "m46-v4-trace.jsonl"
    with _client(trace_path) as client:
        response = client.post("/api/query", json={
            "question": "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。",
            "task": {"action": "start"},
        })
    assert response.status_code == 200
    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    turn = {
        "scenario_id": "T4",
        "turn_id": "T4-rehearsal",
        "task_delta": body["task_delta"],
        "task_state": body["task"]["state"],
        "actions": body["action_attempts"],
        "budget": body["agent_budget"],
        "node_contexts": body["node_contexts"],
        "termination": body["agent_termination"],
        "runtime_identity": body["agent_loop_runtime"],
        "assertions": [["required:b4_child_timeline", "passed"]],
        "source_projection_identity": body["agent_scenario_source_identity"],
    }
    artifact = build_agent_scenario_v4(
        bundle=load_b4_contract_bundle(),
        run_spec={
            "run_id": "m46-v4-rehearsal",
            "seed_identity": "m46-t4-seed-v1",
            "caller_identity": "fixture-caller-safe-v1",
            "knowledge_runtime_identities": body["knowledge_runtimes"],
            "policy_identities": ["document-authorization-policy-v1"],
            "strategy": "subgraph",
        },
        turns=(turn,),
    )
    return artifact, body, trace


def _resign(artifact: dict[str, object]) -> None:
    artifact["run_spec_identity"] = canonical_hash(artifact["run_spec"])
    artifact["artifact_identity"] = canonical_hash({
        key: value for key, value in artifact.items() if key != "artifact_identity"
    })


def test_v4_api_trace_eval_share_one_parent_child_projection(tmp_path: Path) -> None:
    artifact, body, trace = _artifact_from_product_projection(tmp_path)
    turn = artifact["turns"][0]
    assert body["action_attempts"] == trace["action_attempts"] == turn["actions"]
    assert body["agent_scenario_source_identity"] == trace["agent_scenario_source_identity"]
    assert trace["agent_scenario_source_identity"] == turn["source_projection_identity"]
    child = next(
        item["observation"]["diagnostics"]["b4_subgraph"]
        for item in turn["actions"] if item["action_id"] == "collect_document_evidence"
    )
    assert child["termination"] == "answer_ready"
    validate_agent_scenario_v4(artifact, bundle=load_b4_contract_bundle())


@pytest.mark.parametrize("mutation", ["source", "child_budget", "private", "strategy"])
def test_v4_rejects_source_child_budget_private_and_strategy_drift(
    tmp_path: Path, mutation: str
) -> None:
    artifact, _body, _trace = _artifact_from_product_projection(tmp_path)
    turn = artifact["turns"][0]
    child = next(
        item["observation"]["diagnostics"]["b4_subgraph"]
        for item in turn["actions"] if item["action_id"] == "collect_document_evidence"
    )
    if mutation == "source":
        turn["source_projection_identity"] = "tampered"
    elif mutation == "child_budget":
        child["consumption"]["selected"] = 4
    elif mutation == "private":
        child["question"] = "must-not-persist"
    else:
        artifact["run_spec"]["strategy"] = "pipeline"
    _resign(artifact)
    with pytest.raises(ValueError):
        validate_agent_scenario_v4(artifact, bundle=load_b4_contract_bundle())
