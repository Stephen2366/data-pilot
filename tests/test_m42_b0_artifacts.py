"""M42-F 已固化 rehearsal artifact 的身份、非泄露和能力边界。"""

from __future__ import annotations

import json
from pathlib import Path

from engine.phase4b.contracts import load_b0_contract_bundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_contracts import validate_completed_artifact

REPORT_ROOT = Path("eval/reports/m42")


def test_first_business_observation_is_gold_first_real_failure_and_zero_provider() -> None:
    observation = json.loads((REPORT_ROOT / "m42-business-first-observation.json").read_text(encoding="utf-8"))
    unsigned = {key: value for key, value in observation.items() if key != "observation_identity"}
    assert observation["observation_identity"] == canonical_hash(unsigned)
    assert observation["gold_frozen_before_run"] is True
    assert observation["expected_document_keys"] == ["refund_policy_basic", "refund_policy_quality"]
    assert observation["selected_document_keys"] == ["refund_policy_quality"]
    assert observation["all_gold_selected"] is False
    assert observation["budget"] == {"max_candidates": 5, "max_selected": 2, "source": "KnowledgeRequest default"}
    assert observation["provider_calls"] == 0


def test_agent_skeleton_and_repository_reserve_manifest_are_safe() -> None:
    bundle = load_b0_contract_bundle()
    artifact = json.loads((REPORT_ROOT / "m42-agent-scenario-skeleton.json").read_text(encoding="utf-8"))
    validate_completed_artifact(artifact, bundle=bundle)

    reserve = json.loads(Path("eval/cases/agent/phase4b_reserve_manifest.json").read_text(encoding="utf-8"))
    assert reserve["question_count"] == 60
    assert reserve["decision_status"] == "sealed"
    assert reserve["first_unseal_module"] == "M46"
    assert reserve["historical_regression_identity"] == "m34-180-historical-only"
    serialized = json.dumps({"artifact": artifact, "reserve": reserve}, ensure_ascii=False).lower()
    for forbidden in ("gold_answer", "answer_facts", "sql_rows", "model_thought", "authorization"):
        assert forbidden not in serialized
    assert "data-pilot-datasets" not in serialized
