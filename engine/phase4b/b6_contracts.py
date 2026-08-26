"""M48-A：B6 Context Compact 与 Phase 4B assurance 的内容绑定合同。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.phase4b.b5_contracts import load_b5_contract_bundle
from engine.phase4b.identity import canonical_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b6_contracts.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b6_contracts.manifest.json"


class B6ContractError(ValueError):
    """合同缺失、篡改或越过 closed-world 边界时的稳定错误。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class B6ContractBundle:
    """完成 predecessor、shape 与 content identity 校验后的只读合同包。"""

    contract_version: str
    content_identity: str
    payload: Mapping[str, Any]


def _expect_exact(payload: Mapping[str, Any]) -> None:
    """冻结影响 Compact 语义、安全、持久化和最终 assurance 的字段。"""

    expected = {
        "contract_version", "predecessor_contract_identity", "runtime_identity",
        "state_schema_version", "context_schema_version", "compact_schema_version",
        "event_schema_version", "node_context_version", "trigger", "storage",
        "compact_fields", "event_v2_fields", "reason_codes", "forbidden_payload_fields",
        "artifact_versions", "scenarios", "compatibility", "capability_matrix",
    }
    if set(payload) != expected:
        raise B6ContractError("b6_contract_shape_invalid", "root 字段不闭合")
    if payload["contract_version"] != "phase4b-b6-contracts-v1":
        raise B6ContractError("b6_contract_version_unknown", str(payload["contract_version"]))
    if payload["predecessor_contract_identity"] != load_b5_contract_bundle().content_identity:
        raise B6ContractError("b6_predecessor_mismatch", "B5 identity 漂移")
    if payload["runtime_identity"] != "phase4b-task-context-runtime-v1":
        raise B6ContractError("b6_runtime_identity_invalid", "Context runtime identity 漂移")
    if payload["state_schema_version"] != "phase4b-task-state-v2":
        raise B6ContractError("b6_state_schema_invalid", "M48 不改签 TaskState v2")
    if payload["trigger"] != {
        "committed_turns": 5, "candidate_budget_ratio": 0.75,
        "recent_raw_turn_count": 2, "recent_raw_turn_max_bytes": 2048,
        "strategy": "turn_count_or_candidate_node_budget",
    }:
        raise B6ContractError("b6_trigger_contract_invalid", "G48-1 方案 A 漂移")
    if payload["storage"] != {
        "shape": "checkpoint_additive_context_payload",
        "atomicity": "same_claim_compare_and_set_transaction",
        "active_ttl_seconds": 900, "max_context_bytes": 65536,
        "scrub_statuses": ["cleared", "cancelled", "switched", "expired"],
        "probe_database": "datapilot_m48_test",
    }:
        raise B6ContractError("b6_storage_contract_invalid", "G48-2 方案 A 漂移")
    compatibility = payload["compatibility"]
    if compatibility != {
        "legacy_artifacts": "v1_v5_unchanged_readable",
        "legacy_event_v1": "readable_source_incomplete",
        "legacy_non_task_runtime": "unchanged", "pipeline_default": True,
        "subgraph_rollout": "server_controlled_experimental",
        "automatic_strategy_fallback": False, "reserve": "sealed_not_run",
    }:
        raise B6ContractError("b6_compatibility_invalid", "rollout/reserve/legacy 边界漂移")
    artifacts = payload["artifact_versions"]
    if artifacts != {
        "agent_scenario": "phase4b-agent-scenario-artifact-v6",
        "phase_assurance": "phase4b-assurance-artifact-v1",
        "predecessor_agent_scenario": "phase4b-agent-scenario-artifact-v5",
    }:
        raise B6ContractError("b6_artifact_version_invalid", "v6/assurance identity 漂移")
    if len(payload["scenarios"]) != 10 or len(set(payload["scenarios"])) != 10:
        raise B6ContractError("b6_scenarios_invalid", "required Gate 场景不闭合")


def load_b6_contract_bundle(
    path: Path = DEFAULT_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> B6ContractBundle:
    """读取 contract/manifest，并在返回前完成严格内容身份校验。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise B6ContractError("b6_contract_unavailable", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(manifest, dict):
        raise B6ContractError("b6_contract_shape_invalid", "contract/manifest 必须为 object")
    _expect_exact(payload)
    identity = canonical_hash(payload)
    if manifest != {"contract_version": payload["contract_version"], "content_identity": identity}:
        raise B6ContractError("b6_contract_identity_mismatch", "source 与 manifest 不一致")
    return B6ContractBundle(str(payload["contract_version"]), identity, payload)
