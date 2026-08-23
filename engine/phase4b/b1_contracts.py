"""M43-A：加载 B1 task runtime 合同，并在进入运行时前验证内容身份。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.phase4b.identity import canonical_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b1_contracts.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b1_contracts.manifest.json"


class B1ContractError(ValueError):
    """B1 合同缺失、被篡改或形状不闭合时的稳定失败。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class B1ContractBundle:
    """已通过 manifest 与关键闭集检查的 B1 输入。"""

    contract_version: str
    content_identity: str
    payload: Mapping[str, Any]


def load_b1_contract_bundle(path: Path = DEFAULT_PATH, manifest_path: Path = DEFAULT_MANIFEST_PATH) -> B1ContractBundle:
    """读取并验证 B1；v2 消费者不能退回猜测 M42 v1 字段。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise B1ContractError("b1_contract_unavailable", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(manifest, dict):
        raise B1ContractError("b1_contract_shape_invalid", "root/manifest 必须为 object")
    expected = {"contract_version", "predecessor_contract_identity", "runtime_identity", "task_state_version", "understanding_identity", "api", "vocabulary", "scenarios", "capability_matrix"}
    if set(payload) != expected:
        raise B1ContractError("b1_contract_shape_invalid", "root 字段不闭合")
    identity = canonical_hash(payload)
    if manifest != {"contract_version": payload["contract_version"], "content_identity": identity}:
        raise B1ContractError("b1_contract_identity_mismatch", "source 与 manifest 不一致")
    if payload["contract_version"] != "phase4b-b1-contracts-v1":
        raise B1ContractError("b1_contract_version_unknown", str(payload["contract_version"]))
    if payload["api"] != {"path": "/api/query", "envelope": "task", "actions": ["start", "continue", "switch", "cancel"], "legacy_default_unchanged": True}:
        raise B1ContractError("b1_api_contract_invalid", "task envelope 或 legacy 边界漂移")
    ids = [item.get("scenario_id") for item in payload["scenarios"]]
    if ids != ["B1_CANONICAL", "B1_CORRECTION", "B1_SWITCH_CANCEL", "B1_CLARIFY"]:
        raise B1ContractError("b1_scenario_catalog_invalid", "B1 scenario 闭集或顺序漂移")
    if set(payload["vocabulary"]) != {"metric_aliases", "comparison_aliases", "cancel_aliases", "switch_aliases", "correction_aliases"}:
        raise B1ContractError("b1_vocabulary_invalid", "Turn Understanding vocabulary 不闭合")
    if set(payload["capability_matrix"]) != {"implemented", "reserved"}:
        raise B1ContractError("b1_capability_matrix_invalid", "能力矩阵不闭合")
    expected_turn_keys = {
        "T1": {"turn_id", "question", "delta", "periods", "route", "expected_value"},
        "T2": {"turn_id", "question", "delta", "periods", "route", "invalidates_previous_sql", "expected_value"},
        "C1": {"turn_id", "question", "delta", "periods", "route"},
        "S1": {"turn_id", "question", "delta", "periods", "route"},
        "S2": {"turn_id", "question", "delta", "periods", "route"},
        "N1": {"turn_id", "question", "delta", "periods", "route", "clarification_required"},
    }
    for scenario in payload["scenarios"]:
        if not isinstance(scenario, dict) or set(scenario) != {"scenario_id", "turns"}:
            raise B1ContractError("b1_scenario_catalog_invalid", "scenario 字段不闭合")
        for turn in scenario["turns"]:
            turn_id = turn.get("turn_id") if isinstance(turn, dict) else None
            if turn_id not in expected_turn_keys or set(turn) != expected_turn_keys[turn_id]:
                raise B1ContractError("b1_scenario_catalog_invalid", f"turn 字段不闭合: {turn_id}")
    return B1ContractBundle(str(payload["contract_version"]), identity, payload)
