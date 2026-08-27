"""M49-C：Scenario v7 / assurance v2 的独立证据门。"""

from copy import deepcopy

import pytest

from engine.phase4b.b6_contracts import load_b6_contract_bundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_v7_contracts import validate_agent_scenario_v7
from eval.phase4b_assurance_v2 import validate_phase4b_assurance_v2
from scripts.rehearse_m49_phase4b import build_from_evidence_package


def _package(*, include_all: bool = True) -> dict[str, object]:
    """构造最小 evidence package；可故意缺 case 验证 inconclusive 门。"""

    scenarios = load_b6_contract_bundle().payload["scenarios"]
    evidence = {}
    for scenario_id in scenarios if include_all else scenarios[:1]:
        identity = canonical_hash({"scenario": scenario_id, "execution": "probe-safe"})
        locator = f"probe:M49-P2#{scenario_id}"
        evidence[scenario_id] = {
            "status": "passed",
            "observations": {"observed": True},
            "evidence_locator": locator,
            "evidence_identity": identity,
            "assertions": [{
                "assertion_id": f"required:{scenario_id.lower()}",
                "status": "passed",
                "evidence_locator": locator,
                "evidence_identity": identity,
            }],
        }
    contracts = {f"B{i}": f"contract-{i}" for i in range(7)}
    milestone = {
        f"B{i}": {
            "status": "passed",
            "evidence_locator": f"report:M{42 + i}",
            "evidence_identity": f"execution-{i}",
        }
        for i in range(7)
    }
    return {
        "run_id": "m49-test",
        "source_execution_identity": "source-execution",
        "scenario_evidence": evidence,
        "contract_identities": contracts,
        "milestone_evidence": milestone,
    }


def test_missing_execution_cases_make_v7_and_assurance_inconclusive() -> None:
    """缺少真实 observation 时，builder 不能凭合同存在签发 completed。"""

    scenario, assurance = build_from_evidence_package(_package(include_all=False))
    assert scenario["status"] == "inconclusive"
    assert assurance["status"] == "inconclusive"
    assert any(item["status"] == "not_observed" for item in scenario["cases"])


def test_complete_evidence_package_builds_completed_v7_and_assurance() -> None:
    """全部 required case 有独立 locator/identity 时才允许 completed。"""

    bundle = load_b6_contract_bundle()
    scenario, assurance = build_from_evidence_package(_package())
    validate_agent_scenario_v7(scenario, bundle=bundle)
    validate_phase4b_assurance_v2(assurance, bundle=bundle, scenario=scenario)
    assert scenario["status"] == assurance["status"] == "completed"


def test_assurance_rejects_contract_identity_as_execution_evidence() -> None:
    """重新签名也不能让 contract identity 冒充 execution evidence。"""

    bundle = load_b6_contract_bundle()
    scenario, assurance = build_from_evidence_package(_package())
    poisoned = deepcopy(assurance)
    poisoned["capability_matrix"][0]["evidence_identity"] = poisoned["capability_matrix"][0]["contract_identity"]
    unsigned = {key: value for key, value in poisoned.items() if key != "artifact_identity"}
    poisoned["artifact_identity"] = canonical_hash(unsigned)
    with pytest.raises(ValueError, match="phase4b_assurance_v2_contract_self_attestation"):
        validate_phase4b_assurance_v2(poisoned, bundle=bundle, scenario=scenario)


def test_v7_rejects_passed_assertion_without_evidence_locator() -> None:
    """passed assertion 缺定位符时必须失败关闭，不能靠外层签名补票。"""

    bundle = load_b6_contract_bundle()
    scenario, _ = build_from_evidence_package(_package())
    poisoned = deepcopy(scenario)
    poisoned["cases"][0]["assertions"][0]["evidence_locator"] = None
    case = poisoned["cases"][0]
    case["source_identity"] = canonical_hash({key: value for key, value in case.items() if key != "source_identity"})
    unsigned = {key: value for key, value in poisoned.items() if key != "artifact_identity"}
    poisoned["artifact_identity"] = canonical_hash(unsigned)
    with pytest.raises(ValueError, match="agent_scenario_v7_assertion_evidence_missing"):
        validate_agent_scenario_v7(poisoned, bundle=bundle)


def test_v7_rejects_private_payload_even_after_resigning() -> None:
    """重签名也不能把原始问题、rows 或正文塞进正式 evidence artifact。"""

    bundle = load_b6_contract_bundle()
    scenario, _ = build_from_evidence_package(_package())
    poisoned = deepcopy(scenario)
    poisoned["cases"][0]["observations"]["raw_question"] = "私密原问题"
    case = poisoned["cases"][0]
    case["source_identity"] = canonical_hash(
        {key: value for key, value in case.items() if key != "source_identity"}
    )
    unsigned = {key: value for key, value in poisoned.items() if key != "artifact_identity"}
    poisoned["artifact_identity"] = canonical_hash(unsigned)
    with pytest.raises(ValueError, match="agent_scenario_v7_private_payload"):
        validate_agent_scenario_v7(poisoned, bundle=bundle)
