"""M42-A：加载并校验 B0 北极星、兼容矩阵和 action 语义。

这个模块的 interface 只有 ``load_b0_contract_bundle``：调用者不用重复理解 JSON 的闭集字段、
Scenario 完整性或三层 action 语义。复杂校验集中在 implementation，测试也从同一 seam 进入。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.phase4b.identity import canonical_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b0_contracts.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b0_contracts.manifest.json"


class Phase4BContractError(ValueError):
    """B0 输入不闭合时的稳定失败；``reason_code`` 供 Gate 和测试使用。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class B0ContractBundle:
    """已经通过 manifest 与闭集校验的 M42-A 不可变输入。"""

    contract_version: str
    content_identity: str
    payload: Mapping[str, Any]

    @property
    def scenarios(self) -> tuple[Mapping[str, Any], ...]:
        """返回有序 Scenario；顺序是北极星 turn 故事的一部分。"""

        return tuple(self.payload["scenarios"])

    def scenario(self, scenario_id: str) -> Mapping[str, Any]:
        """按稳定 ID 获取唯一 Scenario，未知 ID 失败关闭。"""

        matches = [item for item in self.scenarios if item["scenario_id"] == scenario_id]
        if len(matches) != 1:
            raise Phase4BContractError("scenario_unknown", scenario_id)
        return matches[0]

    def action_views(self, *, corpus: str, observation_present: bool) -> dict[str, tuple[str, ...]]:
        """区分 global catalog、runtime/corpus applicability 与单次 eligible set。

        B0 还没有准入任何恢复动作，因此 ``stop`` 是唯一 eligible；Observation 只能让候选
        进入 applicable 视图，不能把 ``unproven`` 偷换成可执行。
        """

        global_ids = tuple(item["action_id"] for item in self.payload["actions"])
        applicable = tuple(
            item["action_id"]
            for item in self.payload["actions"]
            if item["action_id"] == "stop"
            or (observation_present and ("all" in item["scope"] or corpus in item["scope"]))
        )
        eligible = tuple(
            item["action_id"]
            for item in self.payload["actions"]
            if item["admission_status"] == "always_eligible"
            and item["action_id"] in applicable
        )
        return {"global": global_ids, "applicable": applicable, "eligible": eligible}


def _load_mapping(path: Path, *, reason: str) -> dict[str, Any]:
    """把 IO、编码、JSON 解析错误收敛成稳定合同错误。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Phase4BContractError(reason, f"无法读取 {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Phase4BContractError(reason, f"{path} 顶层必须是 object")
    return payload


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, location: str) -> None:
    """执行 closed-world 字段检查，避免未来靠未知字段猜 runtime family。"""

    actual = set(value)
    if actual != expected:
        raise Phase4BContractError(
            "contract_shape_invalid",
            f"{location} 字段不闭合，missing={sorted(expected-actual)}, unknown={sorted(actual-expected)}",
        )


def _non_empty_unique(values: list[Any], *, location: str) -> None:
    """校验一组业务 ID 非空且无重复，错误统一落到合同值非法。"""

    normalized = [str(item).strip() for item in values]
    if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
        raise Phase4BContractError("contract_value_invalid", f"{location} 必须非空且唯一")


def _validate_bundle(payload: dict[str, Any]) -> None:
    """校验 B0 必须冻结的语义，不提前冻结 B1 TaskState 字段。"""

    _exact_keys(
        payload,
        {"contract_version", "runtime_families", "caller_fixture", "hybrid_operator", "actions", "scenarios", "capability_matrix"},
        location="root",
    )
    if payload["contract_version"] != "phase4b-b0-contracts-v1":
        raise Phase4BContractError("contract_version_unknown", str(payload["contract_version"]))

    caller = payload["caller_fixture"]
    _exact_keys(caller, {"identity", "resolved_roles", "active_sql_role", "tenant_id"}, location="caller_fixture")
    if caller["resolved_roles"] != ["customer_service", "ops"] or caller["active_sql_role"] != "ops":
        raise Phase4BContractError("caller_fixture_invalid", "必须保持最小双角色与 ops active role")

    families = payload["runtime_families"]
    if not isinstance(families, list) or len(families) != 2:
        raise Phase4BContractError("runtime_family_invalid", "必须恰好声明 legacy/agent 两个 family")
    if any(not isinstance(item, dict) for item in families):
        raise Phase4BContractError("runtime_family_invalid", "runtime family 必须逐项为 object")
    _non_empty_unique([item.get("identity") for item in families], location="runtime family")
    if {item.get("kind") for item in families} != {"legacy", "agent"}:
        raise Phase4BContractError("runtime_family_invalid", "legacy/agent family 不闭合")
    family_fields = {"identity", "kind", "request_classes", "budget_contract", "payload_rule"}
    for family in families:
        _exact_keys(family, family_fields, location=f"runtime_family:{family.get('kind')}")
        _non_empty_unique(family["request_classes"], location=f"{family['kind']} request class")
    legacy_classes = set(next(item for item in families if item["kind"] == "legacy")["request_classes"])
    agent_classes = set(next(item for item in families if item["kind"] == "agent")["request_classes"])
    if legacy_classes & agent_classes:
        raise Phase4BContractError("runtime_family_invalid", "旧/new request class 必须互斥")

    hybrid = payload["hybrid_operator"]
    _exact_keys(
        hybrid,
        {"identity", "operator", "sql_requirement", "document_requirement", "required_evidence", "runtime_family", "status"},
        location="hybrid_operator",
    )
    if hybrid["operator"] != "refund_change_and_policy" or hybrid["status"] != "contract_only":
        raise Phase4BContractError("hybrid_operator_invalid", "B0 只能冻结新 operator 语义")
    serialized_hybrid = json.dumps(hybrid, ensure_ascii=False).lower()
    if "2026 年 6 月" in serialized_hybrid or "退款原因排名" in serialized_hybrid:
        raise Phase4BContractError("hybrid_operator_invalid", "新 operator 不得继承 legacy 固定问题")

    actions = payload["actions"]
    if not isinstance(actions, list) or not actions:
        raise Phase4BContractError("action_catalog_invalid", "全局 action catalog 不能为空")
    if any(not isinstance(item, dict) for item in actions):
        raise Phase4BContractError("action_catalog_invalid", "action 必须逐项为 object")
    _non_empty_unique([item.get("action_id") for item in actions], location="action")
    stop = [item for item in actions if item.get("action_id") == "stop"]
    if len(stop) != 1 or stop[0].get("admission_status") != "always_eligible":
        raise Phase4BContractError("action_catalog_invalid", "stop 必须始终可用")
    if any(item.get("action_id") != "stop" and item.get("admission_status") != "unproven" for item in actions):
        raise Phase4BContractError("action_catalog_invalid", "B0 不得提前准入恢复动作")

    scenarios = payload["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) < 7:
        raise Phase4BContractError("scenario_catalog_invalid", "必须包含 T1–T5、extended 和非 happy-path")
    if any(not isinstance(item, dict) for item in scenarios):
        raise Phase4BContractError("scenario_catalog_invalid", "scenario 必须逐项为 object")
    _non_empty_unique([item.get("scenario_id") for item in scenarios], location="scenario")
    canonical_ids = [item.get("scenario_id") for item in scenarios if item.get("class") == "canonical"]
    if canonical_ids != ["T1", "T2", "T3", "T4", "T5"]:
        raise Phase4BContractError("scenario_catalog_invalid", "canonical 顺序必须为 T1→T5")
    required_turn_fields = {
        "turn_id", "question", "delta_category", "evidence_requirements", "invalidates", "route", "action",
        "expected_axes", "required_assertions", "advisory_assertions", "security_identity",
    }
    for scenario in scenarios:
        _exact_keys(scenario, {"scenario_id", "class", "purpose", "turns"}, location=f"scenario:{scenario.get('scenario_id')}")
        if not isinstance(scenario["turns"], list) or not scenario["turns"]:
            raise Phase4BContractError("scenario_catalog_invalid", f"{scenario['scenario_id']} 没有 turn")
        for turn in scenario["turns"]:
            _exact_keys(turn, required_turn_fields, location=f"turn:{turn.get('turn_id')}")
            if len(turn["expected_axes"]) != 4:
                raise Phase4BContractError("scenario_catalog_invalid", f"{turn['turn_id']} 四轴不闭合")


def load_b0_contract_bundle(
    path: Path = DEFAULT_CONTRACT_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> B0ContractBundle:
    """加载 B0 合同并验证独立 manifest；缺失或篡改时在消费前失败关闭。"""

    payload = _load_mapping(path, reason="contract_source_unavailable")
    manifest = _load_mapping(manifest_path, reason="contract_manifest_unavailable")
    _exact_keys(manifest, {"contract_version", "content_identity"}, location="manifest")
    identity = canonical_hash(payload)
    if manifest["contract_version"] != payload.get("contract_version") or manifest["content_identity"] != identity:
        raise Phase4BContractError("contract_identity_mismatch", "B0 source 与 manifest 不一致")
    _validate_bundle(payload)
    return B0ContractBundle(str(payload["contract_version"]), identity, payload)
