"""M48-A：B6 machine contract 的 content-binding 与 closed-world 门。"""

from __future__ import annotations

import json

import pytest

from engine.phase4b.b6_contracts import B6ContractError, load_b6_contract_bundle


def test_b6_contract_freezes_confirmed_a_options() -> None:
    """用户确认的两个 A 方案必须成为机器合同，而不是只留在 plan。"""

    bundle = load_b6_contract_bundle()
    assert bundle.payload["trigger"] == {
        "committed_turns": 5,
        "candidate_budget_ratio": 0.75,
        "recent_raw_turn_count": 2,
        "recent_raw_turn_max_bytes": 2048,
        "strategy": "turn_count_or_candidate_node_budget",
    }
    assert bundle.payload["storage"]["shape"] == "checkpoint_additive_context_payload"
    assert bundle.payload["compatibility"]["pipeline_default"] is True
    assert bundle.payload["compatibility"]["subgraph_rollout"] == "server_controlled_experimental"
    assert bundle.payload["compatibility"]["reserve"] == "sealed_not_run"


def test_b6_contract_rejects_unknown_root_and_tamper(tmp_path) -> None:
    """未知字段或源文件变更都不能借宽松解析穿过 identity 门。"""

    bundle = load_b6_contract_bundle()
    payload = dict(bundle.payload)
    payload["surprise"] = True
    path = tmp_path / "b6.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(B6ContractError, match="b6_contract_shape_invalid"):
        load_b6_contract_bundle(path)


def test_b6_contract_keeps_v1_v5_and_rollout_read_only() -> None:
    """B6 capability available 不能顺手改签旧 artifact 或切换 B4 默认。"""

    payload = load_b6_contract_bundle().payload
    assert payload["artifact_versions"]["predecessor_agent_scenario"] == "phase4b-agent-scenario-artifact-v5"
    assert payload["compatibility"] == {
        "legacy_artifacts": "v1_v5_unchanged_readable",
        "legacy_event_v1": "readable_source_incomplete",
        "legacy_non_task_runtime": "unchanged",
        "pipeline_default": True,
        "subgraph_rollout": "server_controlled_experimental",
        "automatic_strategy_fallback": False,
        "reserve": "sealed_not_run",
    }
