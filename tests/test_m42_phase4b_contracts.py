"""M42-A B0 机器合同、identity、兼容和 action 三层语义。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.phase4b.contracts import Phase4BContractError, load_b0_contract_bundle
from engine.phase4b.identity import canonical_hash


def test_b0_bundle_freezes_north_star_compatibility_and_capability_handoff() -> None:
    """调用者只需加载 bundle，就能消费完整 B0 冻结事实。"""

    bundle = load_b0_contract_bundle()

    assert bundle.content_identity == canonical_hash(bundle.payload)
    assert [item["scenario_id"] for item in bundle.scenarios[:5]] == ["T1", "T2", "T3", "T4", "T5"]
    assert bundle.payload["caller_fixture"]["resolved_roles"] == ["customer_service", "ops"]
    assert bundle.payload["hybrid_operator"]["operator"] == "refund_change_and_policy"
    assert bundle.payload["actions"][0]["action_id"] == "stop"
    no_observation = bundle.action_views(corpus="business_release", observation_present=False)
    with_observation = bundle.action_views(corpus="business_release", observation_present=True)
    assert no_observation == {
        "global": ("stop", "query_rewrite_candidate", "context_expansion_candidate"),
        "applicable": ("stop",),
        "eligible": ("stop",),
    }
    assert with_observation["applicable"] == ("stop", "query_rewrite_candidate")
    assert with_observation["eligible"] == ("stop",)
    assert {item["owner"] for item in bundle.payload["capability_matrix"] if item["status"] == "unavailable"} == {
        "M43", "M44", "M45", "M46", "M47", "M48"
    }


def test_b0_bundle_rejects_content_tamper_unknown_shape_and_unknown_scenario(tmp_path: Path) -> None:
    """manifest、闭集字段和 lookup 三层都 fail closed。"""

    source = json.loads(Path("domain_pack/phase4b/b0_contracts.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path("domain_pack/phase4b/b0_contracts.manifest.json").read_text(encoding="utf-8"))
    source["caller_fixture"]["active_sql_role"] = "customer_service"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(Phase4BContractError, match="identity"):
        load_b0_contract_bundle(tampered, manifest_path)

    source["unexpected"] = True
    manifest["content_identity"] = canonical_hash(source)
    tampered.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(Phase4BContractError, match="shape"):
        load_b0_contract_bundle(tampered, manifest_path)

    with pytest.raises(Phase4BContractError, match="scenario_unknown"):
        load_b0_contract_bundle().scenario("missing")


def test_b0_bundle_rejects_non_object_catalog_item_with_stable_error(tmp_path: Path) -> None:
    """列表项形状损坏也必须返回合同错误，不能泄漏普通 AttributeError。"""

    source = json.loads(Path("domain_pack/phase4b/b0_contracts.json").read_text(encoding="utf-8"))
    source["actions"][0] = "not-an-object"
    source_path = tmp_path / "source.json"
    manifest_path = tmp_path / "manifest.json"
    source_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"contract_version": source["contract_version"], "content_identity": canonical_hash(source)}),
        encoding="utf-8",
    )
    with pytest.raises(Phase4BContractError, match="action_catalog_invalid"):
        load_b0_contract_bundle(source_path, manifest_path)
