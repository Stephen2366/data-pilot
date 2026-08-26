"""M47-F：Scenario v5 六类 durable lifecycle 与抗篡改门。"""

from copy import deepcopy

import pytest

from engine.phase4b.b5_contracts import load_b5_contract_bundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_v5_contracts import build_deterministic_agent_scenario_v5, validate_agent_scenario_v5


def _artifact():
    """从 B5 合同构造标准六场景 artifact。"""

    return build_deterministic_agent_scenario_v5(load_b5_contract_bundle())


def test_v5_covers_all_durable_lifecycles_and_keeps_v1_v4_readable():
    """v5 覆盖六场景且不改写旧 artifact family。"""

    artifact = _artifact()
    validate_agent_scenario_v5(artifact, bundle=load_b5_contract_bundle())
    assert artifact["legacy_artifacts"] == {"v1": "unchanged_readable", "v2": "unchanged_readable", "v3": "unchanged_readable", "v4": "unchanged_readable"}


@pytest.mark.parametrize("mutation", ["source", "private", "reason", "legacy"])
def test_v5_rejects_tampering_and_private_payload(mutation: str):
    """来源、reason、legacy 或私有字段漂移均被拒绝。"""

    artifact = deepcopy(_artifact())
    if mutation == "source":
        artifact["cases"][0]["source_identity"] = "tampered"
    elif mutation == "private":
        artifact["cases"][0]["state_payload"] = {"raw_question": "secret"}
    elif mutation == "reason":
        artifact["cases"][0]["lifecycle"][0]["reason_code"] = "unknown"
    else:
        artifact["legacy_artifacts"]["v4"] = "rewritten"
    artifact["artifact_identity"] = canonical_hash({key: value for key, value in artifact.items() if key != "artifact_identity"})
    with pytest.raises(ValueError):
        validate_agent_scenario_v5(artifact, bundle=load_b5_contract_bundle())
