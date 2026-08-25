"""M45 B3 diagnostic campaign、artifact 与 M46 qualification 合同。

scorer/validator 只消费已经执行完的 action-level Evidence，不会为评分再次调用 Tool。仓库
artifact 使用本模块的安全投影；含正文的 review 材料只能由 Probe runner 写入独立 external
store，并由 SHA-256 manifest 关联。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from engine.phase4b.identity import canonical_hash
from engine.phase4b.rag_diagnostics import FUNNEL_STAGES, RecoveryExecution

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN_PATH = PROJECT_ROOT / "domain_pack" / "phase4b" / "b3_diagnostic_campaign.json"
DEFAULT_MANIFEST_PATH = DEFAULT_CAMPAIGN_PATH.with_name("b3_diagnostic_campaign.manifest.json")
REOPENED_CAMPAIGN_PATH = DEFAULT_CAMPAIGN_PATH.with_name("b3_diagnostic_campaign_v2.json")
REOPENED_MANIFEST_PATH = DEFAULT_CAMPAIGN_PATH.with_name("b3_diagnostic_campaign_v2.manifest.json")
REPAIR_CAMPAIGN_PATH = DEFAULT_CAMPAIGN_PATH.with_name("b3_diagnostic_campaign_v3.json")
REPAIR_MANIFEST_PATH = DEFAULT_CAMPAIGN_PATH.with_name("b3_diagnostic_campaign_v3.manifest.json")
CONTINUATION_CAMPAIGN_PATH = DEFAULT_CAMPAIGN_PATH.with_name("b3_diagnostic_campaign_v4.json")
CONTINUATION_MANIFEST_PATH = DEFAULT_CAMPAIGN_PATH.with_name("b3_diagnostic_campaign_v4.manifest.json")
ALLOWED_ACTIONS = ("query_rewrite_candidate", "context_expansion_candidate", "stop")


class RAGActionDiagnosticError(ValueError):
    """campaign/artifact 的稳定失败类型。"""

    def __init__(self, reason_code: str, message: str = "") -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}" if message else reason_code)


@dataclass(frozen=True)
class DiagnosticScenarioSpec:
    scenario_id: str
    runtime_scope: str
    expected_action: str
    partition: str


@dataclass(frozen=True)
class DiagnosticCampaign:
    """冻结的四题 campaign；identity 对动作、预算、历史输入和 reserve 边界整体签名。"""

    identity: str
    schema_version: str
    scenarios: tuple[DiagnosticScenarioSpec, ...]
    budget: Mapping[str, int]
    historical_inputs: tuple[Mapping[str, str], ...]
    reserve: Mapping[str, str]
    proposal: Mapping[str, Any] | None = None
    predecessor_campaign_identity: str | None = None
    repair: Mapping[str, Any] | None = None
    continuation: Mapping[str, Any] | None = None

    def by_id(self) -> dict[str, DiagnosticScenarioSpec]:
        return {item.scenario_id: item for item in self.scenarios}


def _read_json(path: Path) -> dict[str, Any]:
    """读取 campaign/manifest JSON，并把 IO/格式错误统一成稳定诊断码。"""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RAGActionDiagnosticError("diagnostic_manifest_unavailable", str(path)) from exc
    if not isinstance(value, dict):
        raise RAGActionDiagnosticError("diagnostic_manifest_invalid")
    return value


def load_diagnostic_campaign(
    path: Path = DEFAULT_CAMPAIGN_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    *,
    verify_historical_inputs: bool = True,
) -> DiagnosticCampaign:
    """完整验证 campaign/manifest/historical hashes，且只读检查 reserve 仍 sealed。"""

    payload = _read_json(path)
    manifest = _read_json(manifest_path)
    raw = path.read_bytes()
    if manifest.get("campaign_file") != path.name:
        raise RAGActionDiagnosticError("diagnostic_manifest_invalid")
    if manifest.get("campaign_sha256") != sha256(raw).hexdigest():
        raise RAGActionDiagnosticError("diagnostic_manifest_hash_mismatch")
    identity = canonical_hash(payload)
    if manifest.get("campaign_identity") != identity:
        raise RAGActionDiagnosticError("diagnostic_manifest_identity_mismatch")
    schema_version = payload.get("schema_version")
    if schema_version not in {
        "phase4b-rag-action-diagnostic-campaign-v1",
        "phase4b-rag-action-diagnostic-campaign-v2",
        "phase4b-rag-action-diagnostic-campaign-v3",
        "phase4b-rag-action-diagnostic-campaign-v4",
    }:
        raise RAGActionDiagnosticError("diagnostic_schema_invalid")
    if payload.get("classification") != "diagnostic_dev" or payload.get("baseline_eligible") is not False:
        raise RAGActionDiagnosticError("diagnostic_classification_invalid")
    if tuple(payload.get("actions") or ()) != ALLOWED_ACTIONS:
        raise RAGActionDiagnosticError("diagnostic_action_catalog_invalid")

    raw_scenarios = payload.get("scenarios") or []
    expected_scenario_ids = (
        ("qst_0431",) if schema_version.endswith("v4")
        else ("qst_0461", "qst_0431") if schema_version.endswith("v3")
        else ("T4", "qst_0420", "qst_0431", "qst_0461")
    )
    if not isinstance(raw_scenarios, list) or len(raw_scenarios) != len(expected_scenario_ids):
        raise RAGActionDiagnosticError("diagnostic_scenario_set_invalid")
    scenarios = tuple(
        DiagnosticScenarioSpec(
            scenario_id=str(item.get("scenario_id") or ""),
            runtime_scope=str(item.get("runtime_scope") or ""),
            expected_action=str(item.get("expected_action") or ""),
            partition=str(item.get("partition") or ""),
        )
        for item in raw_scenarios
        if isinstance(item, dict)
    )
    if (
        len(scenarios) != len(expected_scenario_ids)
        or tuple(item.scenario_id for item in scenarios) != expected_scenario_ids
        or len({item.scenario_id for item in scenarios}) != len(expected_scenario_ids)
        or any(item.expected_action not in ALLOWED_ACTIONS[:2] for item in scenarios)
        or (
            not schema_version.endswith(("v3", "v4"))
            and (
                scenarios[0].runtime_scope != "business_release"
                or any(item.runtime_scope != "external_profile" for item in scenarios[1:])
            )
        )
        or (schema_version.endswith(("v3", "v4")) and any(
            item.runtime_scope != "external_profile" for item in scenarios
        ))
    ):
        raise RAGActionDiagnosticError("diagnostic_scenario_set_invalid")

    budget = payload.get("budget")
    expected_budget = {
        "max_scenarios": 4,
        "max_initial_retrievals_per_scenario": 1,
        "max_recovery_actions_per_scenario": 2,
        "max_action_repetitions": 1,
        "max_rewrite_batches": 2,
        "max_candidates_per_batch": 5,
        "max_added_rewrite_evidence": 3,
        "max_expansion_seeds": 2,
        "max_sibling_units_scanned_per_seed": 8,
        "max_added_expansion_evidence": 4,
        "max_embedding_provider_attempts": 8,
        "max_chat_model_calls": 0,
        "max_chat_tokens": 0,
    }
    if schema_version == "phase4b-rag-action-diagnostic-campaign-v2":
        expected_budget.update({
            "max_chat_model_calls": 2,
            "max_chat_tokens": 8000,
            "max_total_provider_attempts": 10,
        })
    elif schema_version == "phase4b-rag-action-diagnostic-campaign-v3":
        expected_budget = {
            "max_scenarios": 2,
            "max_embedding_provider_attempts": 0,
            "max_chat_model_calls": 1,
            "max_chat_tokens": 4123,
            "predecessor_embedding_provider_attempts": 8,
            "predecessor_chat_model_calls": 2,
            "max_total_provider_attempts": 11,
            "max_expansion_seeds": 2,
            "max_sibling_units_scanned_per_seed": 8,
            "max_added_expansion_evidence": 4,
        }
    elif schema_version == "phase4b-rag-action-diagnostic-campaign-v4":
        expected_budget = {
            "max_scenarios": 1,
            "max_embedding_provider_attempts": 0,
            "max_chat_model_calls": 0,
            "max_chat_tokens": 0,
            "predecessor_embedding_provider_attempts": 8,
            "predecessor_chat_model_calls": 3,
            "max_total_provider_attempts": 11,
            "max_expansion_seeds": 2,
            "max_sibling_units_scanned_per_seed": 8,
            "max_added_expansion_evidence": 4,
        }
    if not isinstance(budget, dict) or budget != expected_budget:
        raise RAGActionDiagnosticError("diagnostic_budget_invalid")

    historical = tuple(item for item in payload.get("historical_inputs") or () if isinstance(item, dict))
    expected_historical_count = (
        1 if schema_version.endswith(("v3", "v4"))
        else 5 if schema_version.endswith("v2") else 4
    )
    if len(historical) != expected_historical_count:
        raise RAGActionDiagnosticError("diagnostic_historical_inputs_invalid")
    if verify_historical_inputs:
        for item in historical:
            source = PROJECT_ROOT / str(item.get("path") or "")
            if not source.is_file() or sha256(source.read_bytes()).hexdigest() != item.get("sha256"):
                raise RAGActionDiagnosticError("diagnostic_historical_hash_mismatch", str(item.get("path")))

    reserve = payload.get("reserve")
    if not isinstance(reserve, dict):
        raise RAGActionDiagnosticError("diagnostic_reserve_invalid")
    reserve_manifest = _read_json(PROJECT_ROOT / str(reserve.get("manifest_path") or ""))
    if (
        reserve.get("required_access_state") != "sealed"
        or reserve.get("first_unseal_module") != "M46"
        or reserve_manifest.get("decision_status") != "sealed"
        or reserve_manifest.get("first_unseal_module") != "M46"
    ):
        raise RAGActionDiagnosticError("diagnostic_reserve_not_sealed")

    proposal = payload.get("proposal")
    predecessor = payload.get("predecessor_campaign_identity")
    if schema_version.endswith(("v2", "v3")):
        if proposal != {
            "prompt_identity": "m45-e-evidence-aware-requirement-proposal-v1",
            "outbound_policy_identity": "phase4b-m45-rag-requirement-proposal-outbound-v1",
            "receiver": "qwen_chat",
            "purpose": "rag_requirement_proposal",
            "data_class": "public_benchmark_question_with_authorized_evidence",
            "model": "qwen3.7-plus",
            "max_evidence": 3,
            "max_evidence_chars_each": 4000,
            "max_completion_tokens_each": 1600,
        }:
            raise RAGActionDiagnosticError("diagnostic_proposal_contract_invalid")
        expected_predecessor = (
            "c86e38705382b03d9a99d4349a319be9561d6731b887f01307ad3ddda3f7eaea"
            if schema_version.endswith("v3")
            else "469b5ec01eb78d839e2c621378f53bab0cd29cebc3488f78c9475b13bd2312fe"
        )
        if predecessor != expected_predecessor:
            raise RAGActionDiagnosticError("diagnostic_proposal_contract_invalid")
    elif schema_version.endswith("v4"):
        if (
            proposal is not None
            or predecessor
            != "b41c0d98d330bbf68b6b17d95441e044b9a27c0f66b8ca6594571f5dddcf37a5"
        ):
            raise RAGActionDiagnosticError("diagnostic_continuation_contract_invalid")
    elif proposal is not None or predecessor is not None:
        raise RAGActionDiagnosticError("diagnostic_proposal_contract_invalid")
    repair = payload.get("repair")
    if schema_version.endswith("v3"):
        if repair != {
            "offline_replay_scenario": "qst_0461",
            "provider_revalidation_scenario": "qst_0431",
            "marker_match_mode": "token_overlap",
            "legacy_marker_match_mode": "exact",
            "provider_retry_limit": 0,
        }:
            raise RAGActionDiagnosticError("diagnostic_repair_contract_invalid")
    elif repair is not None:
        raise RAGActionDiagnosticError("diagnostic_repair_contract_invalid")
    continuation = payload.get("continuation")
    if schema_version.endswith("v4"):
        if continuation != {
            "policy": "procedure_boundary_v1",
            "intent_tokens": ["procedure", "workflow", "steps", "checklist"],
            "direction": "forward_only",
            "max_forward_units_per_seed": 1,
            "requires_authority_coordinates": True,
        }:
            raise RAGActionDiagnosticError("diagnostic_continuation_contract_invalid")
    elif continuation is not None:
        raise RAGActionDiagnosticError("diagnostic_continuation_contract_invalid")
    return DiagnosticCampaign(
        identity=identity,
        schema_version=str(schema_version),
        scenarios=scenarios,
        budget={str(key): int(value) for key, value in budget.items()},
        historical_inputs=historical,
        reserve={str(key): str(value) for key, value in reserve.items()},
        proposal=dict(proposal) if isinstance(proposal, dict) else None,
        predecessor_campaign_identity=str(predecessor) if predecessor is not None else None,
        repair=dict(repair) if isinstance(repair, dict) else None,
        continuation=dict(continuation) if isinstance(continuation, dict) else None,
    )


def load_reopened_diagnostic_campaign(*, verify_historical_inputs: bool = True) -> DiagnosticCampaign:
    """读取 C5 review 后 additive v2 campaign；v1 仍由默认 loader 保持不可变。"""

    return load_diagnostic_campaign(
        REOPENED_CAMPAIGN_PATH,
        REOPENED_MANIFEST_PATH,
        verify_historical_inputs=verify_historical_inputs,
    )


def load_repair_diagnostic_campaign(*, verify_historical_inputs: bool = True) -> DiagnosticCampaign:
    """读取 P4 minimal repair v3 campaign；只含一次离线 replay + 一次 provider revalidation。"""

    return load_diagnostic_campaign(
        REPAIR_CAMPAIGN_PATH,
        REPAIR_MANIFEST_PATH,
        verify_historical_inputs=verify_historical_inputs,
    )


def load_continuation_diagnostic_campaign(
    *, verify_historical_inputs: bool = True,
) -> DiagnosticCampaign:
    """读取 M45-H v4 campaign；只有 qst_0431 immutable zero-provider replay。"""

    return load_diagnostic_campaign(
        CONTINUATION_CAMPAIGN_PATH,
        CONTINUATION_MANIFEST_PATH,
        verify_historical_inputs=verify_historical_inputs,
    )


def project_historical_funnel(execution: Mapping[str, Any], assertions: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    """从现有一次 execution/assertion 重建六层漏斗，不补跑旧 pipeline。"""

    statuses = {str(item.get("assertion_id")): str(item.get("status")) for item in assertions}
    mapping = {
        "retrieved": "retrieved_gold",
        "selected": "selected_gold",
        "generation_visible": "generation_visible_gold",
        "cited": "cited_gold",
    }
    result: dict[str, str] = {}
    upstream_closed = False
    first_failure: str | None = None
    for stage in FUNNEL_STAGES:
        if upstream_closed:
            status = "not_observed"
        elif stage in mapping:
            raw = statuses.get(mapping[stage])
            status = "passed" if raw == "passed" else "failed" if raw == "failed" else "not_observed"
        elif stage == "support":
            answer_status = str(execution.get("answer_status") or "")
            status = "passed" if answer_status == "complete" else "failed" if answer_status else "not_observed"
        else:
            status = "passed" if statuses.get("answer_semantic") == "passed" else "failed" if statuses.get("answer_semantic") == "failed" else "not_observed"
        if status != "passed":
            upstream_closed = True
            if status == "failed" and first_failure is None:
                first_failure = stage
        result[stage] = status
    return {"stages": result, "first_failure_layer": first_failure}


def build_completed_artifact(
    *,
    campaign: DiagnosticCampaign,
    executions: tuple[RecoveryExecution, ...],
    runtime_identities: Mapping[str, Mapping[str, Any]],
    probe_evidence: Mapping[str, Mapping[str, Any]],
    external_artifact_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """形成安全 completed artifact；validator 决定 go/no-go，caller 不能自行填 Gate。"""

    payload: dict[str, Any] = {
        "schema_version": "phase4b-rag-action-diagnostic-artifact-v1",
        "classification": "diagnostic_dev",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "executions": [item.safe_projection() for item in executions],
        "runtime_identities": {key: dict(value) for key, value in sorted(runtime_identities.items())},
        "probe_evidence": {key: dict(value) for key, value in sorted(probe_evidence.items())},
        "external_artifact_manifest": dict(external_artifact_manifest),
        "reserve_access_state": "sealed",
    }
    payload["qualification"] = qualify_for_m46(payload, campaign=campaign)
    payload["artifact_identity"] = canonical_hash(payload)
    validate_completed_artifact(payload, campaign=campaign)
    return payload


def qualify_for_m46(payload: Mapping[str, Any], *, campaign: DiagnosticCampaign) -> dict[str, Any]:
    """只有两张 action card、同 runtime 选择和全部 Probe 证据闭合才允许 M46。"""

    executions = payload.get("executions") or []
    by_id = {
        str(item.get("observation", {}).get("scenario_id")): item
        for item in executions
        if isinstance(item, dict) and isinstance(item.get("observation"), dict)
    }
    required_checks: dict[str, bool] = {
        "four_scenarios_complete": set(by_id) == set(campaign.by_id()),
        "reserve_still_sealed": payload.get("reserve_access_state") == "sealed",
        "probe_evidence_complete": set(payload.get("probe_evidence") or {}) == {"M45-P1", "M45-P2", "M45-P3"},
        "external_runtime_same": False,
        "rewrite_card_complete": False,
        "expansion_card_complete": False,
    }
    if required_checks["four_scenarios_complete"]:
        def action_ok(scenario_id: str) -> bool:
            item = by_id[scenario_id]
            observation = item["observation"]
            expected = campaign.by_id()[scenario_id].expected_action
            wrong = ALLOWED_ACTIONS[1] if expected == ALLOWED_ACTIONS[0] else ALLOWED_ACTIONS[0]
            return all((
                item.get("chosen_action") == expected,
                item.get("status") == "completed",
                bool(item.get("evidence_delta", {}).get("added")),
                item.get("progress", {}).get("coverage_increased") is True,
                "stop" in observation.get("eligible_actions", []),
                expected in observation.get("eligible_actions", []),
                wrong in observation.get("rejected_actions", []),
                int(item.get("consumed", {}).get("model_calls", -1)) == 0,
                int(item.get("consumed", {}).get("total_tokens", -1)) == 0,
            ))

        required_checks["rewrite_card_complete"] = all(action_ok(item) for item in ("T4", "qst_0420"))
        required_checks["expansion_card_complete"] = all(action_ok(item) for item in ("qst_0431", "qst_0461"))
        runtimes = payload.get("runtime_identities") or {}
        external = [canonical_hash(runtimes.get(item, {})) for item in ("qst_0420", "qst_0431", "qst_0461")]
        required_checks["external_runtime_same"] = len(set(external)) == 1 and external[0] != canonical_hash({})
    go = all(required_checks.values())
    return {
        "decision": "go_for_M46" if go else "review_required/no_go",
        "required_checks": required_checks,
        "action_cards": {
            "query_rewrite_candidate": "completed" if required_checks["rewrite_card_complete"] else "failed",
            "context_expansion_candidate": "completed" if required_checks["expansion_card_complete"] else "failed",
        },
    }


def validate_completed_artifact(payload: Mapping[str, Any], *, campaign: DiagnosticCampaign) -> None:
    """closed-world 校验 completed artifact，拒绝补字段、预算漂移和伪造 Gate。"""

    required = {
        "schema_version", "classification", "baseline_eligible", "campaign_identity", "executions",
        "runtime_identities", "probe_evidence", "external_artifact_manifest", "reserve_access_state",
        "qualification", "artifact_identity",
    }
    if set(payload) != required:
        raise RAGActionDiagnosticError("diagnostic_artifact_fields_invalid")
    if (
        payload.get("schema_version") != "phase4b-rag-action-diagnostic-artifact-v1"
        or payload.get("classification") != "diagnostic_dev"
        or payload.get("baseline_eligible") is not False
        or payload.get("campaign_identity") != campaign.identity
    ):
        raise RAGActionDiagnosticError("diagnostic_artifact_identity_invalid")
    without_identity = dict(payload)
    observed_identity = without_identity.pop("artifact_identity", None)
    if observed_identity != canonical_hash(without_identity):
        raise RAGActionDiagnosticError("diagnostic_artifact_hash_mismatch")
    expected = qualify_for_m46(payload, campaign=campaign)
    if payload.get("qualification") != expected:
        raise RAGActionDiagnosticError("diagnostic_qualification_invalid")
    executions = payload.get("executions")
    if not isinstance(executions, list) or len(executions) != 4:
        raise RAGActionDiagnosticError("diagnostic_execution_set_invalid")
    scenarios = [str(item.get("observation", {}).get("scenario_id")) for item in executions if isinstance(item, dict)]
    if len(scenarios) != 4 or set(scenarios) != set(campaign.by_id()):
        raise RAGActionDiagnosticError("diagnostic_execution_set_invalid")
    if any(int(item.get("consumed", {}).get("actions", -1)) != 1 for item in executions):
        raise RAGActionDiagnosticError("diagnostic_action_budget_invalid")
    if any(int(item.get("consumed", {}).get("retrieval_batches", 0)) > 2 for item in executions):
        raise RAGActionDiagnosticError("diagnostic_retrieval_budget_invalid")
    if payload.get("reserve_access_state") != "sealed":
        raise RAGActionDiagnosticError("diagnostic_reserve_not_sealed")


REVIEW_PROBE_KEYS = (
    "M45-P1", "M45-P2-R1", "M45-P2-R2", "M45-P2C", "M45-P2D", "M45-P3",
)


def _verified_probe_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """复算单次 Probe identity，并只保留 M45-D 资格判断所需安全字段。"""

    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise RAGActionDiagnosticError("diagnostic_probe_hash_mismatch")
    return {
        "probe_id": payload.get("probe_id"),
        "artifact_identity": observed,
        "campaign_identity": payload.get("campaign_identity"),
        "gate": payload.get("gate"),
        "decision": payload.get("decision"),
        "usage": dict(payload.get("usage") or {}),
        "reserve_access_state": payload.get("reserve_access_state"),
    }


def qualify_review_for_m46(
    *, probe_payloads: Mapping[str, Mapping[str, Any]], campaign: DiagnosticCampaign,
) -> dict[str, Any]:
    """从 immutable Probe 事实推导 no-go/go；不允许报告作者手填结论。"""

    if tuple(probe_payloads) != REVIEW_PROBE_KEYS:
        raise RAGActionDiagnosticError("diagnostic_review_probe_set_invalid")
    p1 = probe_payloads["M45-P1"]
    p2_r2 = probe_payloads["M45-P2-R2"]
    p2d = probe_payloads["M45-P2D"]
    p3 = probe_payloads["M45-P3"]
    p2_scenario = (p2_r2.get("scenarios") or [{}])[0]
    p3_by_id = {
        str(item.get("scenario_id")): item
        for item in p3.get("scenarios") or ()
        if isinstance(item, dict)
    }
    rewrite_card = all((
        p1.get("gate") == "passed",
        p2_scenario.get("execution", {}).get("chosen_action") == "query_rewrite_candidate",
        p2_scenario.get("assertions", {}).get("evidence_gain") is True,
        p2_scenario.get("assertions", {}).get("offline_gold_overlap") is True,
        p2d.get("gate") == "passed",
        p2d.get("assertions", {}).get("remaining_slots_supported") is True,
    ))
    direct_expansion = all(
        p3_by_id.get(scenario_id, {}).get("gate") == "passed"
        and p3_by_id.get(scenario_id, {}).get("execution", {}).get("chosen_action")
        == "context_expansion_candidate"
        for scenario_id in ("qst_0431", "qst_0461")
    )
    expansion_card = p2d.get("gate") == "passed" and direct_expansion
    provider_attempts = sum(
        int((payload.get("usage") or {}).get("embedding_provider_attempts", 0))
        for payload in probe_payloads.values()
    )
    checks = {
        "campaign_current": campaign.identity == "469b5ec01eb78d839e2c621378f53bab0cd29cebc3488f78c9475b13bd2312fe",
        "all_scenarios_observed": set(p3_by_id) == {"qst_0431", "qst_0461"},
        "reserve_still_sealed": all(
            payload.get("reserve_access_state") == "sealed" for payload in probe_payloads.values()
        ),
        "provider_budget_closed": provider_attempts == campaign.budget["max_embedding_provider_attempts"],
        "rewrite_card_complete": rewrite_card,
        "continuation_expansion_passed": p2d.get("gate") == "passed",
        "direct_expansion_card_complete": direct_expansion,
        "expansion_card_complete": expansion_card,
    }
    return {
        "decision": "go_for_M46" if all(checks.values()) else "review_required/no_go",
        "required_checks": checks,
        "action_cards": {
            "query_rewrite_candidate": "completed" if rewrite_card else "failed",
            "context_expansion_candidate": "completed" if expansion_card else "failed",
        },
        "provider_attempts": provider_attempts,
        "failure_reason_codes": [] if expansion_card else [
            "direct_expansion_trigger_not_observed:qst_0431",
            "direct_expansion_trigger_not_observed:qst_0461",
        ],
    }


def build_review_artifact(
    *,
    campaign: DiagnosticCampaign,
    probe_payloads: Mapping[str, Mapping[str, Any]],
    external_artifact_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """构建允许 no-go 的最终安全 review artifact；历史失败与修订 lineage 全保留。"""

    qualification = qualify_review_for_m46(probe_payloads=probe_payloads, campaign=campaign)
    payload: dict[str, Any] = {
        "schema_version": "phase4b-rag-action-diagnostic-review-v1",
        "classification": "diagnostic_dev",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "probe_lineage": {
            key: _verified_probe_projection(value) for key, value in probe_payloads.items()
        },
        "external_artifact_manifest": dict(external_artifact_manifest),
        "qualification": qualification,
        "reserve_access_state": "sealed",
    }
    payload["artifact_identity"] = canonical_hash(payload)
    validate_review_artifact(payload, campaign=campaign, probe_payloads=probe_payloads)
    return payload


def validate_review_artifact(
    payload: Mapping[str, Any],
    *,
    campaign: DiagnosticCampaign,
    probe_payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    """拒绝 no-go 报告缺 Probe、改结论、预算漂移或伪造 identity。"""

    required = {
        "schema_version", "classification", "baseline_eligible", "campaign_identity",
        "probe_lineage", "external_artifact_manifest", "qualification",
        "reserve_access_state", "artifact_identity",
    }
    if set(payload) != required:
        raise RAGActionDiagnosticError("diagnostic_review_fields_invalid")
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise RAGActionDiagnosticError("diagnostic_review_hash_mismatch")
    expected = qualify_review_for_m46(probe_payloads=probe_payloads, campaign=campaign)
    if payload.get("qualification") != expected:
        raise RAGActionDiagnosticError("diagnostic_review_qualification_invalid")
    if (
        payload.get("schema_version") != "phase4b-rag-action-diagnostic-review-v1"
        or payload.get("campaign_identity") != campaign.identity
        or payload.get("reserve_access_state") != "sealed"
        or set(payload.get("probe_lineage") or {}) != set(REVIEW_PROBE_KEYS)
    ):
        raise RAGActionDiagnosticError("diagnostic_review_contract_invalid")


def qualify_reopened_review_for_m46(
    *, predecessor_review: Mapping[str, Any], p4_payload: Mapping[str, Any],
    campaign: DiagnosticCampaign,
) -> dict[str, Any]:
    """把旧 no-go 与 P4 additive Evidence 合并；旧结论是 lineage，不会被原位改写。"""

    if campaign.schema_version != "phase4b-rag-action-diagnostic-campaign-v2":
        raise RAGActionDiagnosticError("diagnostic_reopened_campaign_required")
    predecessor_unsigned = dict(predecessor_review)
    predecessor_identity = predecessor_unsigned.pop("artifact_identity", None)
    if predecessor_identity != canonical_hash(predecessor_unsigned):
        raise RAGActionDiagnosticError("diagnostic_predecessor_review_hash_mismatch")
    p4_projection = _verified_probe_projection(p4_payload)
    old_qualification = predecessor_review.get("qualification") or {}
    scenarios = {
        str(item.get("scenario_id")): item
        for item in p4_payload.get("scenarios") or ()
        if isinstance(item, dict)
    }
    direct_expansion = all(
        scenarios.get(scenario_id, {}).get("gate") == "passed"
        and scenarios.get(scenario_id, {}).get("proposal_status") == "completed"
        and scenarios.get(scenario_id, {}).get("execution", {}).get("chosen_action")
        == "context_expansion_candidate"
        and scenarios.get(scenario_id, {}).get("assertions", {}).get("proposal_gaps_supported") is True
        for scenario_id in ("qst_0431", "qst_0461")
    )
    usage = p4_payload.get("usage") or {}
    chat_calls = int(usage.get("chat_model_calls", -1))
    chat_tokens = int(usage.get("observed_chat_tokens", -1))
    total_attempts = int(old_qualification.get("provider_attempts", -1)) + chat_calls
    checks = {
        "predecessor_campaign_linked": (
            predecessor_review.get("campaign_identity") == campaign.predecessor_campaign_identity
            and predecessor_review.get("qualification", {}).get("decision") == "review_required/no_go"
        ),
        "predecessor_no_go_preserved": (
            old_qualification.get("action_cards") == {
                "query_rewrite_candidate": "completed",
                "context_expansion_candidate": "failed",
            }
            and old_qualification.get("required_checks", {}).get("continuation_expansion_passed") is True
            and old_qualification.get("required_checks", {}).get("direct_expansion_card_complete") is False
        ),
        "p4_campaign_current": p4_projection["campaign_identity"] == campaign.identity,
        "p4_probe_exact": (
            p4_payload.get("probe_id") == "M45-P4"
            and p4_payload.get("gate") == "passed"
            and p4_payload.get("decision") == "continue"
        ),
        "p4_source_linked": (
            p4_payload.get("source_artifact_identity")
            == predecessor_review.get("probe_lineage", {}).get("M45-P3", {}).get("artifact_identity")
        ),
        "p4_two_scenarios_observed": set(scenarios) == {"qst_0431", "qst_0461"},
        "structured_direct_expansion_passed": direct_expansion,
        "proposal_call_budget_closed": chat_calls == campaign.budget["max_chat_model_calls"],
        "proposal_token_budget_respected": 0 <= chat_tokens <= campaign.budget["max_chat_tokens"],
        "p4_zero_extra_retrieval_embedding_composer": (
            int(usage.get("retrieval_calls", -1)) == 0
            and int(usage.get("embedding_provider_attempts", -1)) == 0
            and int(usage.get("composer_calls", -1)) == 0
        ),
        "p4_safe_projection_only": not any(
            key in json.dumps(p4_payload, ensure_ascii=False).casefold()
            for key in ('"prompt"', '"raw_response"', '"content"', '"question"')
        ),
        "total_provider_budget_closed": total_attempts == campaign.budget["max_total_provider_attempts"],
        "reserve_still_sealed": (
            predecessor_review.get("reserve_access_state") == "sealed"
            and p4_payload.get("reserve_access_state") == "sealed"
        ),
    }
    return {
        "decision": "go_for_M46" if all(checks.values()) else "review_required/no_go",
        "required_checks": checks,
        "action_cards": {
            "query_rewrite_candidate": (
                "completed" if old_qualification.get("action_cards", {}).get("query_rewrite_candidate")
                == "completed" else "failed"
            ),
            "context_expansion_candidate": "completed" if direct_expansion else "failed",
        },
        "provider_attempts": {
            "embedding": int(old_qualification.get("provider_attempts", -1)),
            "chat": chat_calls,
            "total": total_attempts,
        },
        "observed_chat_tokens": chat_tokens,
        "failure_reason_codes": [] if direct_expansion else [
            "structured_direct_expansion_not_qualified:qst_0431",
            "structured_direct_expansion_not_qualified:qst_0461",
        ],
    }


def build_reopened_review_artifact(
    *, campaign: DiagnosticCampaign, predecessor_review: Mapping[str, Any],
    p4_payload: Mapping[str, Any], external_artifact_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """构建 additive v2 review；仓库只保留 proposal/action 的安全投影与 hash。"""

    qualification = qualify_reopened_review_for_m46(
        predecessor_review=predecessor_review,
        p4_payload=p4_payload,
        campaign=campaign,
    )
    payload: dict[str, Any] = {
        "schema_version": "phase4b-rag-action-diagnostic-review-v2",
        "classification": "diagnostic_dev",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "predecessor_review_identity": predecessor_review.get("artifact_identity"),
        "p4_probe": _verified_probe_projection(p4_payload),
        "external_artifact_manifest": dict(external_artifact_manifest),
        "qualification": qualification,
        "reserve_access_state": "sealed",
    }
    payload["artifact_identity"] = canonical_hash(payload)
    validate_reopened_review_artifact(
        payload,
        campaign=campaign,
        predecessor_review=predecessor_review,
        p4_payload=p4_payload,
    )
    return payload


def validate_reopened_review_artifact(
    payload: Mapping[str, Any], *, campaign: DiagnosticCampaign,
    predecessor_review: Mapping[str, Any], p4_payload: Mapping[str, Any],
) -> None:
    """删除旧 no-go、改 P4/usage/decision 或把 private prompt 塞回仓库都会失败关闭。"""

    required = {
        "schema_version", "classification", "baseline_eligible", "campaign_identity",
        "predecessor_review_identity", "p4_probe", "external_artifact_manifest",
        "qualification", "reserve_access_state", "artifact_identity",
    }
    if set(payload) != required:
        raise RAGActionDiagnosticError("diagnostic_reopened_review_fields_invalid")
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise RAGActionDiagnosticError("diagnostic_reopened_review_hash_mismatch")
    expected = qualify_reopened_review_for_m46(
        predecessor_review=predecessor_review,
        p4_payload=p4_payload,
        campaign=campaign,
    )
    if payload.get("qualification") != expected:
        raise RAGActionDiagnosticError("diagnostic_reopened_review_qualification_invalid")
    if (
        payload.get("schema_version") != "phase4b-rag-action-diagnostic-review-v2"
        or payload.get("campaign_identity") != campaign.identity
        or payload.get("predecessor_review_identity") != predecessor_review.get("artifact_identity")
        or payload.get("reserve_access_state") != "sealed"
    ):
        raise RAGActionDiagnosticError("diagnostic_reopened_review_contract_invalid")
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    if any(key in serialized for key in ('"prompt"', '"raw_response"', '"content"', '"question"')):
        raise RAGActionDiagnosticError("diagnostic_reopened_review_private_data_present")


def qualify_repair_review_for_m46(
    *, predecessor_review: Mapping[str, Any], p4r_payload: Mapping[str, Any],
    campaign: DiagnosticCampaign,
) -> dict[str, Any]:
    """v3 qualification 同时允许完整 go 或证据不完整 no-go；绝不把 unknown tokens 记 0。"""

    if campaign.schema_version != "phase4b-rag-action-diagnostic-campaign-v3":
        raise RAGActionDiagnosticError("diagnostic_repair_campaign_required")
    for payload, reason in (
        (predecessor_review, "diagnostic_repair_predecessor_hash_mismatch"),
        (p4r_payload, "diagnostic_repair_probe_hash_mismatch"),
    ):
        unsigned = dict(payload)
        observed = unsigned.pop("artifact_identity", None)
        if observed != canonical_hash(unsigned):
            raise RAGActionDiagnosticError(reason)
    scenarios = {
        str(item.get("scenario_id")): item
        for item in p4r_payload.get("scenarios") or ()
        if isinstance(item, dict)
    }
    expansion_passes = {
        scenario_id: (
            scenarios.get(scenario_id, {}).get("gate") == "passed"
            and scenarios.get(scenario_id, {}).get("execution", {}).get("chosen_action")
            == "context_expansion_candidate"
            and scenarios.get(scenario_id, {}).get("assertions", {}).get("proposal_gaps_supported") is True
        )
        for scenario_id in ("qst_0461", "qst_0431")
    }
    usage = p4r_payload.get("usage") or {}
    repair_calls = int(usage.get("chat_model_calls", -1))
    tokens_observed = usage.get("token_usage_observed") is True
    raw_tokens = usage.get("observed_chat_tokens")
    repair_tokens = int(raw_tokens) if tokens_observed and raw_tokens is not None else None
    predecessor_usage = predecessor_review.get("qualification", {}).get("provider_attempts") or {}
    predecessor_total = int(predecessor_usage.get("total", -1))
    checks = {
        "predecessor_campaign_linked": (
            predecessor_review.get("campaign_identity") == campaign.predecessor_campaign_identity
            and predecessor_review.get("qualification", {}).get("decision") == "review_required/no_go"
        ),
        "repair_campaign_current": p4r_payload.get("campaign_identity") == campaign.identity,
        "both_repair_scenarios_observed": set(scenarios) == {"qst_0461", "qst_0431"},
        "qst_0461_offline_expansion_passed": expansion_passes["qst_0461"],
        "qst_0431_revalidation_expansion_passed": expansion_passes["qst_0431"],
        "repair_call_budget_closed": repair_calls == campaign.budget["max_chat_model_calls"],
        "repair_token_usage_observed": tokens_observed,
        "repair_token_budget_respected": (
            repair_tokens is not None and repair_tokens <= campaign.budget["max_chat_tokens"]
        ),
        "total_provider_budget_closed": (
            predecessor_total + repair_calls == campaign.budget["max_total_provider_attempts"]
        ),
        "repair_evidence_complete": p4r_payload.get("evidence_completeness") is None,
        "reserve_still_sealed": (
            predecessor_review.get("reserve_access_state") == "sealed"
            and p4r_payload.get("reserve_access_state") == "sealed"
        ),
    }
    go = all(checks.values())
    return {
        "decision": "go_for_M46" if go else "review_required/no_go",
        "required_checks": checks,
        "action_cards": {
            "query_rewrite_candidate": "completed",
            "context_expansion_candidate": "completed" if all(expansion_passes.values()) else "failed",
        },
        "provider_attempts": {
            "embedding": campaign.budget["predecessor_embedding_provider_attempts"],
            "chat": campaign.budget["predecessor_chat_model_calls"] + repair_calls,
            "total": predecessor_total + repair_calls,
        },
        "repair_observed_chat_tokens": repair_tokens,
        "token_usage_observed": tokens_observed,
        "failure_reason_codes": [] if go else [
            reason for condition, reason in (
                (expansion_passes["qst_0431"], "proposal_no_unsupported_requirement:qst_0431"),
                (tokens_observed, "p4r_token_usage_not_observed"),
                (p4r_payload.get("evidence_completeness") is None, "p4r_failure_artifact_incomplete"),
            ) if not condition
        ],
    }


def build_repair_review_artifact(
    *, campaign: DiagnosticCampaign, predecessor_review: Mapping[str, Any],
    p4r_payload: Mapping[str, Any], external_artifact_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """构建 v3 final review；P4R crash 恢复证据会稳定导出 no-go。"""

    qualification = qualify_repair_review_for_m46(
        predecessor_review=predecessor_review,
        p4r_payload=p4r_payload,
        campaign=campaign,
    )
    payload: dict[str, Any] = {
        "schema_version": "phase4b-rag-action-diagnostic-review-v3",
        "classification": "diagnostic_dev",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "predecessor_review_identity": predecessor_review.get("artifact_identity"),
        "p4r_probe_identity": p4r_payload.get("artifact_identity"),
        "external_artifact_manifest": dict(external_artifact_manifest),
        "qualification": qualification,
        "reserve_access_state": "sealed",
    }
    payload["artifact_identity"] = canonical_hash(payload)
    validate_repair_review_artifact(
        payload,
        campaign=campaign,
        predecessor_review=predecessor_review,
        p4r_payload=p4r_payload,
    )
    return payload


def validate_repair_review_artifact(
    payload: Mapping[str, Any], *, campaign: DiagnosticCampaign,
    predecessor_review: Mapping[str, Any], p4r_payload: Mapping[str, Any],
) -> None:
    """v3 review 的 identity、qualification、lineage 与仓库隐私硬门。"""

    required = {
        "schema_version", "classification", "baseline_eligible", "campaign_identity",
        "predecessor_review_identity", "p4r_probe_identity", "external_artifact_manifest",
        "qualification", "reserve_access_state", "artifact_identity",
    }
    if set(payload) != required:
        raise RAGActionDiagnosticError("diagnostic_repair_review_fields_invalid")
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise RAGActionDiagnosticError("diagnostic_repair_review_hash_mismatch")
    expected = qualify_repair_review_for_m46(
        predecessor_review=predecessor_review,
        p4r_payload=p4r_payload,
        campaign=campaign,
    )
    if payload.get("qualification") != expected:
        raise RAGActionDiagnosticError("diagnostic_repair_review_qualification_invalid")
    if (
        payload.get("schema_version") != "phase4b-rag-action-diagnostic-review-v3"
        or payload.get("campaign_identity") != campaign.identity
        or payload.get("predecessor_review_identity") != predecessor_review.get("artifact_identity")
        or payload.get("p4r_probe_identity") != p4r_payload.get("artifact_identity")
        or payload.get("reserve_access_state") != "sealed"
    ):
        raise RAGActionDiagnosticError("diagnostic_repair_review_contract_invalid")
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    if any(key in serialized for key in ('"prompt"', '"raw_response"', '"content"', '"question"')):
        raise RAGActionDiagnosticError("diagnostic_repair_review_private_data_present")


def qualify_continuation_review_for_m46(
    *, predecessor_review: Mapping[str, Any], p5_payload: Mapping[str, Any],
    campaign: DiagnosticCampaign,
) -> dict[str, Any]:
    """M45-H qualification：继承 qst_0461 pass，并只新增 qst_0431 零 provider 证据。"""

    if campaign.schema_version != "phase4b-rag-action-diagnostic-campaign-v4":
        raise RAGActionDiagnosticError("diagnostic_continuation_campaign_required")
    for payload, reason in (
        (predecessor_review, "diagnostic_continuation_predecessor_hash_mismatch"),
        (p5_payload, "diagnostic_continuation_probe_hash_mismatch"),
    ):
        unsigned = dict(payload)
        observed = unsigned.pop("artifact_identity", None)
        if observed != canonical_hash(unsigned):
            raise RAGActionDiagnosticError(reason)
    predecessor_qualification = predecessor_review.get("qualification") or {}
    scenario = p5_payload.get("scenario") or {}
    assertions = scenario.get("assertions") or {}
    usage = p5_payload.get("usage") or {}
    inherited_attempts = predecessor_qualification.get("provider_attempts") or {}
    checks = {
        "predecessor_v3_no_go_linked": (
            predecessor_review.get("campaign_identity") == campaign.predecessor_campaign_identity
            and predecessor_qualification.get("decision") == "review_required/no_go"
        ),
        "qst_0461_repair_pass_inherited": (
            predecessor_qualification.get("required_checks", {}).get(
                "qst_0461_offline_expansion_passed"
            ) is True
        ),
        "p5_campaign_current": p5_payload.get("campaign_identity") == campaign.identity,
        "p5_qst_0431_only": scenario.get("scenario_id") == "qst_0431",
        "procedure_boundary_triggered": assertions.get("procedure_boundary_triggered") is True,
        "forward_same_document_evidence_gain": (
            assertions.get("forward_same_document_evidence_gain") is True
        ),
        "expected_action_selected": assertions.get("expected_action_selected") is True,
        "rewrite_rejected_and_stop_available": (
            assertions.get("rewrite_rejected") is True
            and assertions.get("stop_available") is True
        ),
        "p5_gate_passed": p5_payload.get("gate") == "passed",
        "zero_new_provider_and_retrieval": (
            usage.get("retrieval_calls") == 0
            and usage.get("embedding_provider_attempts") == 0
            and usage.get("chat_model_calls") == 0
            and usage.get("composer_calls") == 0
            and usage.get("observed_chat_tokens") == 0
            and usage.get("token_usage_observed") is True
        ),
        "total_provider_attempts_unchanged": (
            inherited_attempts.get("total") == campaign.budget["max_total_provider_attempts"]
        ),
        "reserve_still_sealed": (
            predecessor_review.get("reserve_access_state") == "sealed"
            and p5_payload.get("reserve_access_state") == "sealed"
        ),
    }
    go = all(checks.values())
    return {
        "decision": "go_for_M46" if go else "review_required/no_go",
        "required_checks": checks,
        "action_cards": {
            "query_rewrite_candidate": "completed",
            "context_expansion_candidate": "completed" if go else "failed",
        },
        "provider_attempts": {
            "embedding": int(inherited_attempts.get("embedding", -1)),
            "chat": int(inherited_attempts.get("chat", -1)),
            "total": int(inherited_attempts.get("total", -1)),
        },
        "p5_provider_attempts": 0,
        "failure_reason_codes": [] if go else [
            key for key, passed in checks.items() if not passed
        ],
    }


def build_continuation_review_artifact(
    *, campaign: DiagnosticCampaign, predecessor_review: Mapping[str, Any],
    p5_payload: Mapping[str, Any], external_artifact_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """构建 v4 final review，并立即用同一事实重算验证。"""

    payload: dict[str, Any] = {
        "schema_version": "phase4b-rag-action-diagnostic-review-v4",
        "classification": "diagnostic_dev",
        "baseline_eligible": False,
        "campaign_identity": campaign.identity,
        "predecessor_review_identity": predecessor_review.get("artifact_identity"),
        "p5_probe_identity": p5_payload.get("artifact_identity"),
        "external_artifact_manifest": dict(external_artifact_manifest),
        "qualification": qualify_continuation_review_for_m46(
            predecessor_review=predecessor_review,
            p5_payload=p5_payload,
            campaign=campaign,
        ),
        "reserve_access_state": "sealed",
    }
    payload["artifact_identity"] = canonical_hash(payload)
    validate_continuation_review_artifact(
        payload,
        campaign=campaign,
        predecessor_review=predecessor_review,
        p5_payload=p5_payload,
    )
    return payload


def validate_continuation_review_artifact(
    payload: Mapping[str, Any], *, campaign: DiagnosticCampaign,
    predecessor_review: Mapping[str, Any], p5_payload: Mapping[str, Any],
) -> None:
    """v4 review 的 hash、lineage、qualification 与仓库隐私硬门。"""

    required = {
        "schema_version", "classification", "baseline_eligible", "campaign_identity",
        "predecessor_review_identity", "p5_probe_identity", "external_artifact_manifest",
        "qualification", "reserve_access_state", "artifact_identity",
    }
    if set(payload) != required:
        raise RAGActionDiagnosticError("diagnostic_continuation_review_fields_invalid")
    unsigned = dict(payload)
    observed = unsigned.pop("artifact_identity", None)
    if observed != canonical_hash(unsigned):
        raise RAGActionDiagnosticError("diagnostic_continuation_review_hash_mismatch")
    expected = qualify_continuation_review_for_m46(
        predecessor_review=predecessor_review,
        p5_payload=p5_payload,
        campaign=campaign,
    )
    if payload.get("qualification") != expected:
        raise RAGActionDiagnosticError("diagnostic_continuation_review_qualification_invalid")
    if (
        payload.get("schema_version") != "phase4b-rag-action-diagnostic-review-v4"
        or payload.get("campaign_identity") != campaign.identity
        or payload.get("predecessor_review_identity")
        != predecessor_review.get("artifact_identity")
        or payload.get("p5_probe_identity") != p5_payload.get("artifact_identity")
        or payload.get("reserve_access_state") != "sealed"
    ):
        raise RAGActionDiagnosticError("diagnostic_continuation_review_contract_invalid")
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    if any(key in serialized for key in ('"prompt"', '"raw_response"', '"content"', '"question"')):
        raise RAGActionDiagnosticError("diagnostic_continuation_review_private_data_present")
