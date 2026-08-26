"""M47-F：durable checkpoint/event lifecycle 的 additive Agent Scenario v5。"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.b5_contracts import B5ContractBundle
from engine.phase4b.identity import canonical_hash

ARTIFACT_VERSION = "phase4b-agent-scenario-artifact-v5"
RUN_SPEC_FIELDS = {
    "run_id", "contract_identity", "predecessor_artifact_version", "backend_identity",
    "state_schema_version", "event_schema_version",
}
CASE_FIELDS = {"scenario_id", "checkpoint", "lifecycle", "runtime_identity", "assertions", "source_identity"}
CHECKPOINT_FIELDS = {"task_safe_ref", "task_version", "status", "state_identity"}
LIFECYCLE_FIELDS = {
    "task_safe_ref", "action", "reason_code", "version_before", "version_after",
    "state_identity", "previous_task_safe_ref", "checkpoint_safe_ref", "resume_source",
    "storage_outcome", "schema_version",
}


def build_agent_scenario_v5(*, bundle: B5ContractBundle, run_spec: Mapping[str, Any], cases: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    """签发 completed v5 artifact；不调用 Tool/provider，也不改写 v1–v4。"""

    normalized = {**dict(run_spec), "contract_identity": bundle.content_identity}
    legacy = {f"v{version}": "unchanged_readable" for version in range(1, 5)}
    unsigned = {
        "artifact_version": ARTIFACT_VERSION, "status": "completed", "run_spec": normalized,
        "run_spec_identity": canonical_hash(normalized), "legacy_artifacts": legacy,
        "cases": [dict(item) for item in cases],
    }
    artifact = {**unsigned, "artifact_identity": canonical_hash(unsigned)}
    validate_agent_scenario_v5(artifact, bundle=bundle)
    return artifact


def validate_agent_scenario_v5(payload: Mapping[str, Any], *, bundle: B5ContractBundle) -> None:
    """验证 closed-world shape、六类 lifecycle、同源 identity 与隐私边界。"""

    if set(payload) != {"artifact_version", "status", "run_spec", "run_spec_identity", "legacy_artifacts", "cases", "artifact_identity"}:
        raise ValueError("agent_scenario_v5_shape_invalid")
    if payload["artifact_version"] != ARTIFACT_VERSION or payload["status"] != "completed":
        raise ValueError("agent_scenario_v5_version_invalid")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise ValueError("agent_scenario_v5_identity_mismatch")
    spec = payload["run_spec"]
    if not isinstance(spec, dict) or set(spec) != RUN_SPEC_FIELDS or spec["contract_identity"] != bundle.content_identity:
        raise ValueError("agent_scenario_v5_run_spec_invalid")
    if spec["predecessor_artifact_version"] != "phase4b-agent-scenario-artifact-v4":
        raise ValueError("agent_scenario_v5_predecessor_invalid")
    if payload["run_spec_identity"] != canonical_hash(spec):
        raise ValueError("agent_scenario_v5_run_spec_identity_mismatch")
    if payload["legacy_artifacts"] != {f"v{version}": "unchanged_readable" for version in range(1, 5)}:
        raise ValueError("agent_scenario_v5_legacy_invalid")
    cases = payload["cases"]
    if not isinstance(cases, list) or {case.get("scenario_id") for case in cases if isinstance(case, dict)} != set(bundle.payload["scenarios"]):
        raise ValueError("agent_scenario_v5_cases_incomplete")
    for case in cases:
        _validate_case(case, bundle=bundle)
    _reject_private(payload)


def _validate_case(case: Mapping[str, Any], *, bundle: B5ContractBundle) -> None:
    """校验一个 durable lifecycle case 的 closed-world 形状与来源 hash。"""

    if set(case) != CASE_FIELDS or set(case["checkpoint"]) != CHECKPOINT_FIELDS:
        raise ValueError("agent_scenario_v5_case_invalid")
    lifecycle = case["lifecycle"]
    if not isinstance(lifecycle, list) or not lifecycle:
        raise ValueError("agent_scenario_v5_lifecycle_invalid")
    for fact in lifecycle:
        if set(fact) != LIFECYCLE_FIELDS or fact["schema_version"] != bundle.payload["event_schema_version"]:
            raise ValueError("agent_scenario_v5_lifecycle_invalid")
        if fact["reason_code"] not in bundle.payload["reason_codes"]:
            raise ValueError("agent_scenario_v5_reason_invalid")
    source = canonical_hash({key: value for key, value in case.items() if key not in {"assertions", "source_identity"}})
    if case["source_identity"] != source:
        raise ValueError("agent_scenario_v5_source_identity_mismatch")
    assertions = case["assertions"]
    if not isinstance(assertions, list) or not assertions or any(not isinstance(item, list) or len(item) != 2 or item[1] != "passed" for item in assertions):
        raise ValueError("agent_scenario_v5_assertions_invalid")


def _reject_private(value: Any, *, key: str = "") -> None:
    """递归拒绝 v5 artifact 不得长期保存的私有执行数据。"""

    denied = {"task_id", "state_payload", "raw_question", "raw_answer", "rows", "prompt", "token", "credential", "secret"}
    if key.casefold() in denied:
        raise ValueError("agent_scenario_v5_private_payload")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _reject_private(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _reject_private(child)


def sign_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """给 rehearsal/test 的单一签名入口，避免各处自行拼 hash。"""

    unsigned = {key: value for key, value in case.items() if key not in {"assertions", "source_identity"}}
    return {**dict(case), "source_identity": canonical_hash(unsigned)}


def build_deterministic_agent_scenario_v5(bundle: B5ContractBundle) -> dict[str, Any]:
    """构造 required Gate 共用的六场景零 provider 样本。"""

    def fact(action: str, reason: str, before: int | None, after: int | None, *, previous: str | None = None) -> dict[str, Any]:
        """构造 deterministic rehearsal 使用的标准 lifecycle fact。"""

        return {
            "task_safe_ref": "task:safe-a", "action": action, "reason_code": reason,
            "version_before": before, "version_after": after, "state_identity": "state:a",
            "previous_task_safe_ref": previous, "checkpoint_safe_ref": "task:safe-a",
            "resume_source": "database", "storage_outcome": "committed",
            "schema_version": "phase4b-task-boundary-event-v1",
        }

    scenarios = {
        "RESTART_RESUME": [fact("started", "task_started", None, 1), fact("active", "task_active", 1, 3)],
        "MULTIWORKER_CONFLICT": [fact("active", "task_active", 3, 5), fact("rejected", "task_version_conflict", None, None)],
        "WRONG_OWNER": [fact("rejected", "task_unavailable", None, None)],
        "EXPIRED": [fact("expired", "task_expired", 1, 1)],
        "CLEAR": [fact("cleared", "task_cleared", 1, 3)],
        "SWITCH": [fact("switched", "task_switched", 3, 1, previous="task:safe-old")],
    }
    cases = tuple(sign_case({
        "scenario_id": scenario,
        "checkpoint": {"task_safe_ref": "task:safe-a", "task_version": facts[-1]["version_after"], "status": facts[-1]["action"], "state_identity": "state:a"},
        "lifecycle": facts,
        "runtime_identity": {"identity": "phase4b-mysql-task-boundary-v1", "durability": "database_durable"},
        "assertions": [[f"required:{scenario.lower()}", "passed"]],
    }) for scenario, facts in scenarios.items())
    return build_agent_scenario_v5(
        bundle=bundle,
        run_spec={
            "run_id": "m47-v5-deterministic", "predecessor_artifact_version": "phase4b-agent-scenario-artifact-v4",
            "backend_identity": "phase4b-mysql-task-boundary-v1", "state_schema_version": "phase4b-task-state-v2",
            "event_schema_version": "phase4b-task-boundary-event-v1",
        },
        cases=cases,
    )
