"""M42-D：Phase 4B Agent Scenario completed artifact skeleton。

M41 负责可信的单题 RAG Eval；这里在其“一次执行后评分、closed-world、安全投影”纪律上
增加 sequence/turn 层。它使用独立 schema 和 identity，绝不读取或改签 M41 artifact。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from engine.phase4b.contracts import B0ContractBundle
from engine.phase4b.identity import canonical_hash, canonical_json

AGENT_SCENARIO_SCHEMA = "phase4b-agent-scenario-v1"
AssertionStatus = Literal["passed", "failed", "not_observed"]


class AgentScenarioContractError(ValueError):
    """sequence、turn、execution、assertion 或 identity 不闭合。"""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class TurnExecutionEvidence:
    """一个 turn 的安全执行投影；不保存 answer、SQL rows、正文或模型 Thought。"""

    turn_id: str
    execution_status: str
    evidence_kinds: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    assertion_results: tuple[tuple[str, AssertionStatus], ...]


@dataclass(frozen=True)
class SequenceExecutionEvidence:
    """一条 sequence 的唯一物理执行；turn 顺序必须与 catalog 完全一致。"""

    scenario_id: str
    execution_id: str
    turns: tuple[TurnExecutionEvidence, ...]


def build_b0_fixture_evidence(bundle: B0ContractBundle) -> tuple[SequenceExecutionEvidence, ...]:
    """为 B0 未接真实 Agent runtime 的阶段构造确定性合同证据。

    这里的 ``passed`` 只表示 M42 已冻结对应输入/边界，不表示 M43–M48 能力已经可执行。
    capability matrix 仍把那些能力明确标为 unavailable。
    """

    executions: list[SequenceExecutionEvidence] = []
    for scenario in bundle.scenarios:
        turns: list[TurnExecutionEvidence] = []
        for turn in scenario["turns"]:
            assertion_ids = [*turn["required_assertions"], *turn["advisory_assertions"]]
            route = turn["route"]
            evidence_kinds = tuple(kind for kind in ("sql", "document") if kind in " ".join(turn["evidence_requirements"]))
            turns.append(
                TurnExecutionEvidence(
                    turn_id=turn["turn_id"],
                    execution_status="contract_rehearsed" if route != "hybrid" else "unavailable_until_M44",
                    evidence_kinds=evidence_kinds,
                    evidence_refs=tuple(f"safe:{route}:{turn['turn_id']}" for _ in evidence_kinds),
                    assertion_results=tuple((assertion_id, "passed") for assertion_id in assertion_ids),
                )
            )
        executions.append(
            SequenceExecutionEvidence(
                scenario_id=scenario["scenario_id"],
                execution_id=f"m42-fixture:{scenario['scenario_id']}",
                turns=tuple(turns),
            )
        )
    return tuple(executions)


def build_completed_artifact(
    *,
    bundle: B0ContractBundle,
    run_id: str,
    executions: tuple[SequenceExecutionEvidence, ...],
    runtime_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """形成 completed artifact，并在返回前从同一 interface 做闭集验证。"""

    if not run_id.strip():
        raise AgentScenarioContractError("run_id_invalid", "run_id 不能为空")
    selected = [item["scenario_id"] for item in bundle.scenarios]
    run_spec = {
        "run_id": run_id,
        "selected_scenario_ids": selected,
        "contract_identity": bundle.content_identity,
        "runtime_identity": dict(runtime_identity),
    }
    execution_payloads = []
    for execution in executions:
        # canonical JSON round-trip 同时把 tuple 转成真正 JSON array，避免 Python 内存对象与
        # 落盘后对象形状不同，进而出现“构建时通过、重新加载后失败”的 Eval 事故。
        value = json.loads(canonical_json(asdict(execution)))
        value["execution_identity"] = canonical_hash(value)
        execution_payloads.append(value)
    unsigned = {
        "schema_version": AGENT_SCENARIO_SCHEMA,
        "status": "completed",
        "run_spec": run_spec,
        "run_spec_identity": canonical_hash(run_spec),
        "executions": execution_payloads,
        "capability_matrix": bundle.payload["capability_matrix"],
    }
    artifact = {**unsigned, "artifact_identity": canonical_hash(unsigned)}
    validate_completed_artifact(artifact, bundle=bundle)
    return artifact


def _assert_exact_keys(value: Mapping[str, Any], expected: set[str], *, location: str) -> None:
    """执行 artifact closed-world 字段校验，拒绝静默接纳未知投影。"""

    if set(value) != expected:
        raise AgentScenarioContractError("agent_artifact_shape_invalid", location)


def validate_completed_artifact(payload: Mapping[str, Any], *, bundle: B0ContractBundle) -> None:
    """证明 selected sequence/turn/execution/assertion 和全部 identity 恰好闭合。"""

    _assert_exact_keys(
        payload,
        {"schema_version", "status", "run_spec", "run_spec_identity", "executions", "capability_matrix", "artifact_identity"},
        location="root",
    )
    if payload["schema_version"] != AGENT_SCENARIO_SCHEMA or payload["status"] != "completed":
        raise AgentScenarioContractError("agent_artifact_version_invalid", "schema/status 非法")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise AgentScenarioContractError("agent_artifact_identity_mismatch", "artifact hash 不匹配")
    run_spec = payload["run_spec"]
    if not isinstance(run_spec, dict) or payload["run_spec_identity"] != canonical_hash(run_spec):
        raise AgentScenarioContractError("agent_run_spec_identity_mismatch", "RunSpec identity 不匹配")
    if run_spec.get("contract_identity") != bundle.content_identity:
        raise AgentScenarioContractError("agent_contract_identity_mismatch", "B0 contract 漂移")

    expected_scenarios = [item["scenario_id"] for item in bundle.scenarios]
    if run_spec.get("selected_scenario_ids") != expected_scenarios:
        raise AgentScenarioContractError("agent_selection_mismatch", "selected scenario 顺序/闭集不匹配")
    executions = payload["executions"]
    if not isinstance(executions, list) or [item.get("scenario_id") for item in executions] != expected_scenarios:
        raise AgentScenarioContractError("agent_execution_closed_world_failed", "sequence execution 缺失、额外、重复或乱序")

    for scenario, execution in zip(bundle.scenarios, executions):
        _assert_exact_keys(execution, {"scenario_id", "execution_id", "turns", "execution_identity"}, location="execution")
        unsigned_execution = {key: value for key, value in execution.items() if key != "execution_identity"}
        if execution["execution_identity"] != canonical_hash(unsigned_execution):
            raise AgentScenarioContractError("agent_execution_identity_mismatch", execution["scenario_id"])
        if not str(execution["execution_id"]).strip():
            raise AgentScenarioContractError("agent_execution_closed_world_failed", "execution_id 为空")
        expected_turns = scenario["turns"]
        turns = execution["turns"]
        if [turn.get("turn_id") for turn in turns] != [turn["turn_id"] for turn in expected_turns]:
            raise AgentScenarioContractError("agent_turn_closed_world_failed", execution["scenario_id"])
        for expected_turn, turn in zip(expected_turns, turns):
            _assert_exact_keys(
                turn,
                {"turn_id", "execution_status", "evidence_kinds", "evidence_refs", "assertion_results"},
                location="turn",
            )
            expected_assertions = [*expected_turn["required_assertions"], *expected_turn["advisory_assertions"]]
            actual_assertions = turn["assertion_results"]
            if [item[0] for item in actual_assertions] != expected_assertions:
                raise AgentScenarioContractError("agent_assertion_closed_world_failed", turn["turn_id"])
            if any(item[1] not in {"passed", "failed", "not_observed"} for item in actual_assertions):
                raise AgentScenarioContractError("agent_assertion_status_invalid", turn["turn_id"])
            if len(turn["evidence_kinds"]) != len(turn["evidence_refs"]):
                raise AgentScenarioContractError("agent_evidence_projection_invalid", turn["turn_id"])


def render_capability_report(payload: Mapping[str, Any], *, output: Path) -> None:
    """生成安全的人读矩阵；只展示状态和 owner，不展开执行上下文。"""

    lines = ["# Phase 4B B0 Capability Matrix", "", f"- Artifact: `{payload['artifact_identity']}`", "", "| Capability | Status | Owner |", "|---|---|---|"]
    for row in payload["capability_matrix"]:
        lines.append(f"| {row['capability']} | {row['status']} | {row['owner']} |")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
