"""M48-E：从一次连续执行投影 Context Compact Agent Scenario v6。"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.b6_contracts import B6ContractBundle
from engine.phase4b.identity import canonical_hash

ARTIFACT_VERSION = "phase4b-agent-scenario-artifact-v6"
ROOT_FIELDS = {
    "artifact_version", "status", "run_spec", "run_spec_identity", "legacy_artifacts",
    "cases", "artifact_identity",
}
RUN_FIELDS = {
    "run_id", "contract_identity", "predecessor_artifact_version", "context_schema_version",
    "compact_schema_version", "event_schema_version", "source_execution_identity",
}
CASE_FIELDS = {"scenario_id", "source", "observations", "assertions", "source_identity"}
DENIED = {
    "task_id", "owner_ref", "state_payload", "context_payload", "raw_question", "raw_answer",
    "rows", "document_body", "retrieved_chunks", "prompt", "thought", "authorization_header",
    "credential", "secret", "token",
}


def sign_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """给单个 scenario 的安全来源签名，assertions 不参与 source identity。"""

    unsigned = {key: value for key, value in case.items() if key not in {"assertions", "source_identity"}}
    return {**dict(case), "source_identity": canonical_hash(unsigned)}


def build_agent_scenario_v6(
    *, bundle: B6ContractBundle, run_spec: Mapping[str, Any], cases: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """签发 completed v6；调用方必须提供完整十场景和同源 execution identity。"""

    normalized = {**dict(run_spec), "contract_identity": bundle.content_identity}
    unsigned = {
        "artifact_version": ARTIFACT_VERSION, "status": "completed",
        "run_spec": normalized, "run_spec_identity": canonical_hash(normalized),
        "legacy_artifacts": {f"v{version}": "unchanged_readable" for version in range(1, 6)},
        "cases": [dict(item) for item in cases],
    }
    artifact = {**unsigned, "artifact_identity": canonical_hash(unsigned)}
    validate_agent_scenario_v6(artifact, bundle=bundle)
    return artifact


def validate_agent_scenario_v6(payload: Mapping[str, Any], *, bundle: B6ContractBundle) -> None:
    """闭合校验版本、predecessor、十场景、同源签名与 private payload 禁区。"""

    if set(payload) != ROOT_FIELDS:
        raise ValueError("agent_scenario_v6_shape_invalid")
    if payload["artifact_version"] != ARTIFACT_VERSION or payload["status"] != "completed":
        raise ValueError("agent_scenario_v6_version_invalid")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise ValueError("agent_scenario_v6_identity_mismatch")
    spec = payload["run_spec"]
    if not isinstance(spec, dict) or set(spec) != RUN_FIELDS:
        raise ValueError("agent_scenario_v6_run_spec_invalid")
    if spec["contract_identity"] != bundle.content_identity:
        raise ValueError("agent_scenario_v6_contract_mismatch")
    if spec["predecessor_artifact_version"] != "phase4b-agent-scenario-artifact-v5":
        raise ValueError("agent_scenario_v6_predecessor_invalid")
    if payload["run_spec_identity"] != canonical_hash(spec):
        raise ValueError("agent_scenario_v6_run_spec_identity_mismatch")
    if payload["legacy_artifacts"] != {f"v{version}": "unchanged_readable" for version in range(1, 6)}:
        raise ValueError("agent_scenario_v6_legacy_invalid")
    cases = payload["cases"]
    if not isinstance(cases, list) or [item.get("scenario_id") for item in cases] != bundle.payload["scenarios"]:
        raise ValueError("agent_scenario_v6_cases_incomplete_or_unordered")
    for case in cases:
        if set(case) != CASE_FIELDS or not case["observations"]:
            raise ValueError("agent_scenario_v6_case_invalid")
        source = canonical_hash({key: value for key, value in case.items() if key not in {"assertions", "source_identity"}})
        if case["source_identity"] != source:
            raise ValueError("agent_scenario_v6_source_identity_mismatch")
        assertions = case["assertions"]
        if not assertions or any(not isinstance(item, list) or len(item) != 2 or item[1] != "passed" for item in assertions):
            raise ValueError("agent_scenario_v6_assertions_invalid")
    _reject_private(payload)


def _reject_private(value: Any, *, key: str = "") -> None:
    """递归拒绝 Eval artifact 长期保存 raw task/context/answer/tool payload。"""

    if key.casefold() in DENIED:
        raise ValueError("agent_scenario_v6_private_payload")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _reject_private(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _reject_private(child)

