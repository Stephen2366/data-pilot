"""M47-A：B5 durable task state 的 additive、内容绑定合同。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.phase4b.b4_contracts import load_b4_contract_bundle
from engine.phase4b.identity import canonical_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b5_contracts.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b5_contracts.manifest.json"


class B5ContractError(ValueError):
    """合同缺失、篡改或越过 closed-world 边界时的稳定错误。"""

    def __init__(self, reason_code: str, message: str) -> None:
        """记录稳定合同错误码，不向调用方伪装为普通缺文件。"""

        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class B5ContractBundle:
    """完成 hash 与 predecessor 校验后的只读 B5 合同包。"""

    contract_version: str
    content_identity: str
    payload: Mapping[str, Any]


def _expect_exact(payload: Mapping[str, Any]) -> None:
    """集中冻结会影响 durable state 安全与验收的 closed-world 字段。"""

    expected = {
        "contract_version", "predecessor_contract_identity", "runtime_identity",
        "state_schema_version", "event_schema_version", "storage", "ownership",
        "statuses", "reason_codes", "persisted_state_fields", "forbidden_payload_fields",
        "artifact_versions", "scenarios", "capability_matrix",
    }
    if set(payload) != expected:
        raise B5ContractError("b5_contract_shape_invalid", "root 字段不闭合")
    if payload["contract_version"] != "phase4b-b5-contracts-v1":
        raise B5ContractError("b5_contract_version_unknown", str(payload["contract_version"]))
    if payload["predecessor_contract_identity"] != load_b4_contract_bundle().content_identity:
        raise B5ContractError("b5_predecessor_mismatch", "B4 identity 漂移")
    if payload["runtime_identity"] != "phase4b-mysql-task-boundary-v1":
        raise B5ContractError("b5_runtime_identity_invalid", "durable runtime identity 漂移")
    if payload["state_schema_version"] != "phase4b-task-state-v2":
        raise B5ContractError("b5_state_schema_invalid", "M47 不得静默迁移 TaskState v2")
    storage = payload["storage"]
    if storage != {
        "product_backend": "mysql", "test_backend": "memory_explicit_only",
        "atomicity": "database_compare_and_set", "active_ttl_seconds": 900,
        "tombstone_retention_seconds": 86400, "max_state_bytes": 65536,
        "payload_scrub": ["cleared", "cancelled", "switched", "expired"],
    }:
        raise B5ContractError("b5_storage_contract_invalid", "G47-1 方案 A 漂移")
    if payload["ownership"] != {
        "dimensions": ["owner_ref", "tenant_ref", "active_role"],
        "wrong_owner_policy": "uniform_task_unavailable", "task_lookup": "sha256_task_key",
        "claim_fencing": "single_use_token_hash",
    }:
        raise B5ContractError("b5_ownership_contract_invalid", "owner/tenant/role/fencing 漂移")
    if payload["statuses"] != ["active", "claimed", "cancelled", "switched", "cleared", "expired"]:
        raise B5ContractError("b5_status_catalog_invalid", "lifecycle status 必须闭合")
    if payload["reason_codes"] != [
        "task_started", "task_claimed", "task_active", "task_cancelled", "task_switched",
        "task_cleared", "task_expired", "task_unavailable", "task_not_active",
        "task_version_conflict", "task_owner_mismatch", "task_storage_unavailable",
        "task_schema_incompatible", "task_payload_too_large",
    ]:
        raise B5ContractError("b5_reason_catalog_invalid", "reason code 必须闭合")
    if payload["persisted_state_fields"] != [
        "owner_ref", "generation", "status", "goal", "constraints", "pending_questions",
        "requirements", "evidence_requirements", "route", "evidence", "termination",
        "last_action_attempts", "last_budget", "last_termination", "state_version",
    ]:
        raise B5ContractError("b5_persisted_fields_invalid", "TaskState allowlist 漂移")
    if payload["scenarios"] != ["RESTART_RESUME", "MULTIWORKER_CONFLICT", "WRONG_OWNER", "EXPIRED", "CLEAR", "SWITCH"]:
        raise B5ContractError("b5_scenarios_invalid", "required Gate 场景不完整")
    if payload["artifact_versions"]["agent_scenario"] != "phase4b-agent-scenario-artifact-v5":
        raise B5ContractError("b5_artifact_version_invalid", "Scenario v5 未冻结")


def load_b5_contract_bundle(path: Path = DEFAULT_PATH, manifest_path: Path = DEFAULT_MANIFEST_PATH) -> B5ContractBundle:
    """读取 contract/manifest，并在返回前完成内容身份校验。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise B5ContractError("b5_contract_unavailable", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(manifest, dict):
        raise B5ContractError("b5_contract_shape_invalid", "contract/manifest 必须为 object")
    _expect_exact(payload)
    identity = canonical_hash(payload)
    if manifest != {"contract_version": payload["contract_version"], "content_identity": identity}:
        raise B5ContractError("b5_contract_identity_mismatch", "source 与 manifest 不一致")
    return B5ContractBundle(str(payload["contract_version"]), identity, payload)
