"""M46-A：加载 B4 RAG Subgraph 的 additive、内容绑定合同。

★ B2 的历史父预算只描述一次固定检索，不能被原地改写成多步行为；本模块单独冻结
"一次父级 Knowledge action + 有界 child ledger" 的身份。这样旧 artifact 仍可按原语义复核。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.phase4b.b2_contracts import load_b2_contract_bundle
from engine.phase4b.identity import canonical_hash

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b4_contracts.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b4_contracts.manifest.json"


class B4ContractError(ValueError):
    """B4 合同缺失、篡改或越过 closed-world 边界时的稳定错误。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class B4ContractBundle:
    """已经过 predecessor、hash 与关键上限校验的 B4 合同包。"""

    contract_version: str
    content_identity: str
    payload: Mapping[str, Any]


def _expect_exact(payload: Mapping[str, Any]) -> None:
    """集中校验不能在实现便利下漂移的 B4 核心事实。"""

    expected_root = {
        "contract_version", "predecessor_contract_identity", "b3_campaign_identity",
        "runtime_identity", "strategies", "parent_budget", "child_budget", "actions",
        "terminations", "proposal", "external_requirement_formation", "reserve", "artifact_versions", "scenarios",
        "capability_matrix",
    }
    if set(payload) != expected_root:
        raise B4ContractError("b4_contract_shape_invalid", "root 字段不闭合")
    predecessor = load_b2_contract_bundle().content_identity
    if payload["contract_version"] != "phase4b-b4-contracts-v1":
        raise B4ContractError("b4_contract_version_unknown", str(payload["contract_version"]))
    if payload["predecessor_contract_identity"] != predecessor:
        raise B4ContractError("b4_predecessor_mismatch", "B2 identity 漂移")
    if payload["b3_campaign_identity"] != "15cda06ec378b8a200e5aa6edd1b38e3af23cc256269fc07629873def36be708":
        raise B4ContractError("b4_b3_campaign_mismatch", "M45 action card identity 漂移")
    if payload["strategies"] != ["pipeline", "subgraph"]:
        raise B4ContractError("b4_strategy_catalog_invalid", "strategy catalog 必须闭合")
    if payload["actions"] != ["query_rewrite_candidate", "context_expansion_candidate", "stop"]:
        raise B4ContractError("b4_action_catalog_invalid", "不得扩大 recovery action")
    parent = payload["parent_budget"]
    if not isinstance(parent, dict) or parent != {
        "identity": "phase4b-b4-parent-knowledge-action-v1",
        "max_actions": 3,
        "max_deep_tools": 3,
        "max_sql_actions": 3,
        "max_knowledge_actions": 1,
        "max_repairs_per_requirement": 1,
        "max_retrieval_batches": 3,
        "max_candidates": 15,
        "max_selected": 3,
        "max_generation_visible": 3,
        "max_model_calls": 6,
        "max_total_tokens": 24000,
    }:
        raise B4ContractError("b4_parent_budget_invalid", "父账必须保留 B2 顶层次数且能汇总 child 实际消费")
    child = payload["child_budget"]
    if not isinstance(child, dict) or child != {
        "identity": "phase4b-b4-rag-child-budget-v1",
        "max_recovery_actions": 2,
        "max_initial_retrieval_batches": 1,
        "max_rewrite_retrieval_batches": 2,
        "max_total_retrieval_batches": 3,
        "max_candidates_per_batch": 5,
        "max_total_candidates": 15,
        "max_unique_merged_evidence": 10,
        "max_selected": 3,
        "max_generation_visible": 3,
        "max_expansion_seeds": 2,
        "max_sibling_units_scanned_per_seed": 8,
        "max_added_expansion_evidence": 4,
        "max_proposal_calls": 1,
        "max_model_calls": 1,
        "max_total_tokens": 24000,
    }:
        raise B4ContractError("b4_child_budget_invalid", "B3 action card 与 B4 child budget 不匹配")
    proposal = payload["proposal"]
    if not isinstance(proposal, dict) or proposal != {
        "enabled_for": "external_profile_only",
        "purpose": "rag_recovery_requirement_proposal",
        "data_class": "public_benchmark_question_with_authorized_evidence",
        "schema_version": "phase4b-b4-question-obligation-proposal-v1",
        "prompt_identity": "phase4b-b4-question-obligation-prompt-v2",
        "outbound_policy_identity": "phase4b-b4-recovery-requirement-proposal-outbound-v1",
        "max_slots": 2,
        "business_outbound": "denied",
    }:
        raise B4ContractError("b4_proposal_contract_invalid", "G46-1 方案 A 发生漂移")
    formation = payload["external_requirement_formation"]
    if not isinstance(formation, dict) or formation != {
        "identity": "phase4b-b4-external-requirement-formation-v2",
        "enabled_for": "external_profile_only",
        "precedence": ["procedure_boundary_v1", "structured_question_obligations", "typed_stop"],
        "input_fields": ["question", "authorized_document_evidence", "max_requirements"],
        "max_requirements": 2,
        "question_grounding": "exact_source_spans",
        "qualifier_validation": "server_downgrade_unsupported_current_authority_to_none",
        "evidence_grounding": "server_question_document_meaningful_token_overlap",
        "answer_value_policy": "question_values_are_constraints_model_values_denied",
        "focused_query_owner": "deterministic_server_assembler",
        "coverage_owner": "deterministic_single_authorized_document_validator",
        "formed_requirement_fields": [
            "slot_signature",
            "supplier_identity",
            "formation_reason_category",
            "allowed_recovery_actions",
            "coverage_semantics",
        ],
    }:
        raise B4ContractError("b4_external_requirement_formation_invalid", "C2-ERF 边界发生漂移")
    reserve = payload["reserve"]
    if not isinstance(reserve, dict) or reserve.get("source_ledger_mutable") is not False:
        raise B4ContractError("b4_reserve_immutability_invalid", "原 reserve ledger 必须只读")
    if reserve.get("source_identity") != "f70c5fcafa3d7601d2700a5d98dc2a2647532c236dd1a56e6a48008fa100e505":
        raise B4ContractError("b4_reserve_identity_mismatch", "reserve identity 漂移")


def load_b4_contract_bundle(
    path: Path = DEFAULT_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> B4ContractBundle:
    """从单一入口读取、校验并返回可供 B4 runtime/Eval 共用的合同。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise B4ContractError("b4_contract_unavailable", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(manifest, dict):
        raise B4ContractError("b4_contract_shape_invalid", "contract/manifest 必须为 object")
    _expect_exact(payload)
    identity = canonical_hash(payload)
    if manifest != {"contract_version": payload["contract_version"], "content_identity": identity}:
        raise B4ContractError("b4_contract_identity_mismatch", "source 与 manifest 不一致")
    return B4ContractBundle(str(payload["contract_version"]), identity, payload)
