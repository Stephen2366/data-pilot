"""M49-C：把真实 execution evidence 投影为 Agent Scenario v7。

v7 不再接受“builder 说通过”作为证据。每个 required assertion 都要携带
observation status、证据定位符和独立 evidence identity；没有观察到就只能
得到 ``not_observed``，并把整个 artifact 收敛为 ``inconclusive``。
"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.b6_contracts import B6ContractBundle
from engine.phase4b.identity import canonical_hash

ARTIFACT_VERSION = "phase4b-agent-scenario-artifact-v7"
STATUSES = {"passed", "failed", "not_observed"}
ROOT_FIELDS = {
    "artifact_version", "status", "run_spec", "run_spec_identity",
    "legacy_artifacts", "cases", "artifact_identity",
}
RUN_FIELDS = {
    "run_id", "contract_identity", "predecessor_artifact_version",
    "source_execution_identity",
}
CASE_FIELDS = {
    "scenario_id", "required", "status", "observations", "evidence_locator",
    "evidence_identity", "assertions", "source_identity",
}
ASSERTION_FIELDS = {"assertion_id", "status", "evidence_locator", "evidence_identity"}
DENIED = {
    "task_id", "owner_ref", "state_payload", "context_payload", "raw_question",
    "raw_answer", "rows", "document_body", "retrieved_chunks", "prompt", "thought",
    "authorization_header", "credential", "secret", "token",
}


def _overall_status(cases: list[Mapping[str, Any]]) -> str:
    """required case 的三态决定 artifact 三态；optional case 不得掩盖失败。"""

    required = [item for item in cases if item["required"]]
    if any(item["status"] == "failed" for item in required):
        return "failed"
    if any(item["status"] == "not_observed" for item in required):
        return "inconclusive"
    return "completed"


def sign_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """签名 observation、assertion 与证据 locator，防止只改 passed 字样。"""

    unsigned = {key: value for key, value in case.items() if key != "source_identity"}
    return {**dict(unsigned), "source_identity": canonical_hash(unsigned)}


def build_agent_scenario_v7(
    *, bundle: B6ContractBundle, run_spec: Mapping[str, Any], cases: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """构建三态 v7；状态由 cases 推导，调用方不能直接指定 completed。"""

    normalized = {**dict(run_spec), "contract_identity": bundle.content_identity}
    normalized_cases = [dict(item) for item in cases]
    unsigned = {
        "artifact_version": ARTIFACT_VERSION,
        "status": _overall_status(normalized_cases),
        "run_spec": normalized,
        "run_spec_identity": canonical_hash(normalized),
        "legacy_artifacts": {f"v{version}": "unchanged_readable" for version in range(1, 7)},
        "cases": normalized_cases,
    }
    artifact = {**unsigned, "artifact_identity": canonical_hash(unsigned)}
    validate_agent_scenario_v7(artifact, bundle=bundle)
    return artifact


def validate_agent_scenario_v7(payload: Mapping[str, Any], *, bundle: B6ContractBundle) -> None:
    """验证闭集 case、三态推导、证据绑定、签名与 private payload 禁区。"""

    if set(payload) != ROOT_FIELDS or payload.get("artifact_version") != ARTIFACT_VERSION:
        raise ValueError("agent_scenario_v7_shape_invalid")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise ValueError("agent_scenario_v7_identity_mismatch")
    spec = payload["run_spec"]
    if not isinstance(spec, dict) or set(spec) != RUN_FIELDS:
        raise ValueError("agent_scenario_v7_run_spec_invalid")
    if spec["contract_identity"] != bundle.content_identity:
        raise ValueError("agent_scenario_v7_contract_mismatch")
    if spec["predecessor_artifact_version"] != "phase4b-agent-scenario-artifact-v6":
        raise ValueError("agent_scenario_v7_predecessor_invalid")
    if payload["run_spec_identity"] != canonical_hash(spec):
        raise ValueError("agent_scenario_v7_run_spec_identity_mismatch")
    if payload["legacy_artifacts"] != {f"v{version}": "unchanged_readable" for version in range(1, 7)}:
        raise ValueError("agent_scenario_v7_legacy_invalid")

    cases = payload["cases"]
    if not isinstance(cases, list) or [item.get("scenario_id") for item in cases] != bundle.payload["scenarios"]:
        raise ValueError("agent_scenario_v7_cases_incomplete_or_unordered")
    for case in cases:
        if set(case) != CASE_FIELDS or case["status"] not in STATUSES or case["required"] is not True:
            raise ValueError("agent_scenario_v7_case_invalid")
        assertions = case["assertions"]
        if not isinstance(assertions, list) or not assertions:
            raise ValueError("agent_scenario_v7_assertions_missing")
        if any(set(item) != ASSERTION_FIELDS or item["status"] not in STATUSES for item in assertions):
            raise ValueError("agent_scenario_v7_assertion_invalid")
        assertion_statuses = {item["status"] for item in assertions}
        expected = "failed" if "failed" in assertion_statuses else (
            "not_observed" if "not_observed" in assertion_statuses else "passed"
        )
        if case["status"] != expected:
            raise ValueError("agent_scenario_v7_case_status_mismatch")
        if case["status"] == "not_observed":
            if case["observations"] or case["evidence_locator"] is not None or case["evidence_identity"] is not None:
                raise ValueError("agent_scenario_v7_not_observed_has_evidence")
            if any(item["evidence_locator"] is not None or item["evidence_identity"] is not None for item in assertions):
                raise ValueError("agent_scenario_v7_not_observed_assertion_has_evidence")
        else:
            if not case["observations"] or not case["evidence_locator"] or not case["evidence_identity"]:
                raise ValueError("agent_scenario_v7_observation_evidence_missing")
            if any(not item["evidence_locator"] or not item["evidence_identity"] for item in assertions):
                raise ValueError("agent_scenario_v7_assertion_evidence_missing")
        expected_source = canonical_hash({key: value for key, value in case.items() if key != "source_identity"})
        if case["source_identity"] != expected_source:
            raise ValueError("agent_scenario_v7_source_identity_mismatch")
    if payload["status"] != _overall_status(cases):
        raise ValueError("agent_scenario_v7_status_mismatch")
    _reject_private(payload)


def _reject_private(value: Any, *, key: str = "") -> None:
    """递归拒绝任务原文、rows、正文、Prompt、Thought 和凭据。"""

    if key.casefold() in DENIED:
        raise ValueError("agent_scenario_v7_private_payload")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _reject_private(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _reject_private(child)
