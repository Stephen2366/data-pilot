"""M44-A：加载 B2 Decision Loop 合同并验证内容身份与闭集语义。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.phase4b.identity import canonical_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b2_contracts.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b2_contracts.manifest.json"


class B2ContractError(ValueError):
    """B2 合同缺失、篡改或越出已确认方案时的稳定错误。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class B2ContractBundle:
    """调用方已经可以安全消费的 B2 合同包。"""

    contract_version: str
    content_identity: str
    payload: Mapping[str, Any]


def load_b2_contract_bundle(
    path: Path = DEFAULT_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> B2ContractBundle:
    """从一个深 interface 完成 IO、hash、形状和已确认参数校验。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise B2ContractError("b2_contract_unavailable", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(manifest, dict):
        raise B2ContractError("b2_contract_shape_invalid", "root/manifest 必须为 object")
    expected = {
        "contract_version", "predecessor_contract_identity", "runtime_identity", "task_state_version",
        "budget_profile", "knowledge_scopes", "actions", "terminations", "scenarios", "capability_matrix",
    }
    if set(payload) != expected:
        raise B2ContractError("b2_contract_shape_invalid", "root 字段不闭合")
    identity = canonical_hash(payload)
    if manifest != {"contract_version": payload["contract_version"], "content_identity": identity}:
        raise B2ContractError("b2_contract_identity_mismatch", "source 与 manifest 不一致")
    if payload["contract_version"] != "phase4b-b2-contracts-v1":
        raise B2ContractError("b2_contract_version_unknown", str(payload["contract_version"]))
    if payload["predecessor_contract_identity"] != "383fbf51016c1baf525657552eb14dbb507edce5ba1d566c1557d3ac6f7e9d32":
        raise B2ContractError("b2_predecessor_mismatch", "B1 identity 漂移")
    if payload["task_state_version"] != "phase4b-task-state-v2":
        raise B2ContractError("b2_task_state_version_invalid", "M44 必须使用 additive v2")
    if payload["knowledge_scopes"] != ["business_release", "external_profile"]:
        raise B2ContractError("b2_knowledge_scope_invalid", "知识 runtime scope 不闭合")
    if payload["actions"] != [
        "collect_sql_evidence", "repair_sql_evidence", "collect_document_evidence", "clarify", "stop"
    ]:
        raise B2ContractError("b2_action_catalog_invalid", "Action catalog 或顺序漂移")
    budget = payload["budget_profile"]
    expected_budget = {
        "identity", "max_actions", "max_deep_tools", "max_sql_actions", "max_knowledge_actions",
        "max_repairs_per_requirement", "max_retrieval_batches", "max_candidates", "max_selected",
        "max_generation_visible", "max_model_calls", "max_total_tokens",
    }
    if not isinstance(budget, dict) or set(budget) != expected_budget:
        raise B2ContractError("b2_budget_shape_invalid", "budget profile 字段不闭合")
    if budget != {
        "identity": "phase4b-b2-parent-budget-conservative-v1",
        "max_actions": 3, "max_deep_tools": 3, "max_sql_actions": 3,
        "max_knowledge_actions": 1, "max_repairs_per_requirement": 1,
        "max_retrieval_batches": 1, "max_candidates": 5, "max_selected": 3,
        "max_generation_visible": 3, "max_model_calls": 6, "max_total_tokens": 24000,
    }:
        raise B2ContractError("b2_budget_value_invalid", "必须保持用户确认的保守父预算")
    if payload["terminations"] != [
        "answer_ready", "clarification_required", "no_progress", "budget_exhausted", "unsafe",
        "external_unavailable", "unrecoverable", "agent_loop_contract_failure",
    ]:
        raise B2ContractError("b2_termination_catalog_invalid", "termination catalog 漂移")
    if payload["scenarios"] != [
        "T3", "T4", "T5", "SQL_DIALECT_REPAIR", "NO_PROGRESS", "BUDGET_STOP",
        "UNSAFE", "EXTERNAL_UNAVAILABLE",
    ]:
        raise B2ContractError("b2_scenario_catalog_invalid", "scenario catalog 漂移")
    if set(payload["capability_matrix"]) != {"implemented", "reserved"}:
        raise B2ContractError("b2_capability_matrix_invalid", "能力矩阵不闭合")
    if payload["capability_matrix"] != {
        "implemented": [
            "top_level_decision_loop", "typed_parent_budget", "knowledge_runtime_resolver",
            "sql_dialect_repair", "agent_scenario_v3",
        ],
        "reserved": [
            "rag_recovery_action_admission", "bounded_rag_subgraph", "durable_task_state",
            "context_compact",
        ],
    }:
        raise B2ContractError("b2_capability_matrix_invalid", "能力矩阵内容漂移")
    return B2ContractBundle(str(payload["contract_version"]), identity, payload)
