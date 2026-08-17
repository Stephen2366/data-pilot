"""M40 P7：把独立合同与跨路径 Trace 收成一份 closed-world technical assurance。

它不是新的评分器，也不重跑 M34。每个 family 仍保有自己的分母和断言；这里仅验证
“本轮 P7 要求的证据是否恰好齐全、身份是否可回查、P6 no-go 是否被如实保留”。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Literal

from engine.rag.catalog import build_staged_catalog
from eval.harness_contracts import HARNESS_CONTRACT_VERSION, run_harness_contracts
from eval.harness_followup_contracts import FOLLOW_UP_CONTRACT_VERSION, run_harness_followup_contracts
from eval.harness_hybrid_contracts import HYBRID_CONTRACT_VERSION, run_hybrid_contracts
from eval.harness_turn_contracts import HARNESS_TURN_CONTRACT_VERSION, run_harness_turn_contracts
from eval.phase4_contracts import project_required_gate as project_security_gate
from eval.phase4_contracts import run_phase4_contract_suite
from eval.rag_answer_contracts import RAG_ANSWER_CONTRACT_VERSION, project_required_gate as project_answer_gate
from eval.rag_answer_contracts import run_rag_answer_contract_suite
from eval.rag_retrieval_contracts import RAG_RETRIEVAL_CONTRACT_VERSION, project_required_gate as project_retrieval_gate
from eval.rag_retrieval_contracts import run_rag_retrieval_contract_suite

ASSURANCE_FORMAT = "phase4-assurance-v1"
REHEARSAL_FORMAT = "phase4-trace-rehearsal-v1"
REHEARSAL_SCENARIOS = ("sql", "rag", "hybrid", "clarification_resume", "safety_rejection")
REQUIRED_FAMILIES = (
    "p1_security_release", "p2_rag_retrieval", "p2_rag_answer", "p3_harness", "p4_turn",
    "p4_followup", "p5_hybrid", "p6_no_go", "p7_trace_rehearsal",
)


def _hash(payload: object) -> str:
    """对安全 JSON 投影计算稳定身份；所有闭合校验复用同一种序列化规则。"""

    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class TraceRehearsalEvidence:
    """一条跨路径演示的安全执行事实，不含答案正文、rows、thread id 或文档内容。"""

    scenario_id: str
    trace_count: int
    response_trace_ids_match: bool
    axes_match: bool
    evidence_or_lifecycle_valid: bool
    runtime_status: str
    no_sensitive_payload: bool
    execution_identity: str


@dataclass(frozen=True)
class TraceRehearsalArtifact:
    """C2 的 closed-world artifact；每条 Scenario 的多个检查只读同次 API/Trace 事实。"""

    format: str
    selected_scenario_ids: tuple[str, ...]
    execution_evidence: tuple[TraceRehearsalEvidence, ...]
    artifact_identity: str

    def unsigned_payload(self) -> dict[str, object]:
        return {"format": self.format, "selected_scenario_ids": list(self.selected_scenario_ids),
                "execution_evidence": [asdict(item) for item in self.execution_evidence]}


def build_trace_rehearsal_artifact(evidence: tuple[TraceRehearsalEvidence, ...]) -> TraceRehearsalArtifact:
    """构造并验证五路径 rehearsal；不能用额外、重复或漏路径制造表面通过。"""

    artifact = TraceRehearsalArtifact(REHEARSAL_FORMAT, REHEARSAL_SCENARIOS, evidence, "")
    artifact = replace(artifact, artifact_identity=_hash(artifact.unsigned_payload()))
    validate_trace_rehearsal_artifact(artifact)
    return artifact


def rehearsal_artifact_to_json(artifact: TraceRehearsalArtifact) -> dict[str, object]:
    """把已验证的 rehearsal 转成可由 assurance CLI 读取的安全 JSON。"""

    validate_trace_rehearsal_artifact(artifact)
    return {**artifact.unsigned_payload(), "artifact_identity": artifact.artifact_identity}


def rehearsal_artifact_from_json(payload: object) -> TraceRehearsalArtifact:
    """从 JSON 恢复 C2 artifact，并在进入 C3 前先严格验证其闭合性。"""

    if not isinstance(payload, dict):
        raise ValueError("P7 rehearsal JSON 必须是 object")
    raw_evidence = payload.get("execution_evidence")
    if not isinstance(raw_evidence, list):
        raise ValueError("P7 rehearsal JSON 缺少 execution_evidence")
    try:
        artifact = TraceRehearsalArtifact(
            format=str(payload.get("format")),
            selected_scenario_ids=tuple(payload.get("selected_scenario_ids", ())),
            execution_evidence=tuple(TraceRehearsalEvidence(**item) for item in raw_evidence),
            artifact_identity=str(payload.get("artifact_identity")),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("P7 rehearsal JSON 字段不合法") from exc
    validate_trace_rehearsal_artifact(artifact)
    return artifact


def validate_trace_rehearsal_artifact(artifact: TraceRehearsalArtifact) -> None:
    """C2 闭合门：五条路径都要同源、安全且拥有完整 runtime identity。"""

    if artifact.format != REHEARSAL_FORMAT or artifact.selected_scenario_ids != REHEARSAL_SCENARIOS:
        raise ValueError("P7 rehearsal contract/scenario 不匹配")
    if tuple(item.scenario_id for item in artifact.execution_evidence) != REHEARSAL_SCENARIOS:
        raise ValueError("P7 rehearsal execution 缺失、重复或乱序")
    for item in artifact.execution_evidence:
        if item.trace_count <= 0 or not item.execution_identity or not all((item.response_trace_ids_match, item.axes_match,
                                              item.evidence_or_lifecycle_valid, item.no_sensitive_payload)):
            raise ValueError("P7 rehearsal response/Trace/Evidence/lifecycle 合同失败")
        if item.runtime_status != "complete":
            raise ValueError("P7 rehearsal 缺少完整 runtime identity")
    if _hash(artifact.unsigned_payload()) != artifact.artifact_identity:
        raise ValueError("P7 rehearsal artifact identity 不匹配")


@dataclass(frozen=True)
class AssuranceEntry:
    """一个 required family 的最小登记，不复制其内部 assertion 或质量分数。"""

    family: str
    contract_version: str
    artifact_identity: str
    status: Literal["passed"]


@dataclass(frozen=True)
class Phase4AssuranceArtifact:
    """C3 最终 technical gate；passed 不等同用户已人工验收或生产就绪。"""

    format: str
    entries: tuple[AssuranceEntry, ...]
    artifact_identity: str

    def unsigned_payload(self) -> dict[str, object]:
        return {"format": self.format, "entries": [asdict(item) for item in self.entries]}


def run_phase4_assurance(*, root: Path, rehearsal: TraceRehearsalArtifact, m39_audit_path: Path) -> Phase4AssuranceArtifact:
    """★ 运行当前 deterministic family，并把 M39 frozen decision 以只读方式登记。

    M27 历史 artifact 与 M34 的 retrieval/answer 数字没有槽位，避免把不同合同拼成总分。
    """

    validate_trace_rehearsal_artifact(rehearsal)
    security = run_phase4_contract_suite(staged=build_staged_catalog(), root=root / "p1-security")
    if project_security_gate(security).status != "passed":
        raise ValueError("P1 security Gate 未通过")
    retrieval = run_rag_retrieval_contract_suite()
    if project_retrieval_gate(retrieval).status != "passed":
        raise ValueError("P2 retrieval Gate 未通过")
    answer = run_rag_answer_contract_suite()
    if project_answer_gate(answer).status != "passed":
        raise ValueError("P2 answer Gate 未通过")
    harness = run_harness_contracts()
    turn = run_harness_turn_contracts()
    followup = run_harness_followup_contracts()
    hybrid = run_hybrid_contracts()
    audit_identity = _validate_m39_no_go(m39_audit_path)
    entries = (
        AssuranceEntry("p1_security_release", security.contract_version, security.artifact_identity, "passed"),
        AssuranceEntry("p2_rag_retrieval", retrieval.contract_version, retrieval.artifact_identity, "passed"),
        AssuranceEntry("p2_rag_answer", answer.contract_version, answer.artifact_identity, "passed"),
        AssuranceEntry("p3_harness", HARNESS_CONTRACT_VERSION, harness.artifact_identity, "passed"),
        AssuranceEntry("p4_turn", HARNESS_TURN_CONTRACT_VERSION, turn.artifact_identity, "passed"),
        AssuranceEntry("p4_followup", FOLLOW_UP_CONTRACT_VERSION, followup.artifact_identity, "passed"),
        AssuranceEntry("p5_hybrid", HYBRID_CONTRACT_VERSION, hybrid.artifact_identity, "passed"),
        AssuranceEntry("p6_no_go", "phase4-rag-subgraph-readiness-v1", audit_identity, "passed"),
        AssuranceEntry("p7_trace_rehearsal", rehearsal.format, rehearsal.artifact_identity, "passed"),
    )
    artifact = Phase4AssuranceArtifact(ASSURANCE_FORMAT, entries, "")
    artifact = replace(artifact, artifact_identity=_hash(artifact.unsigned_payload()))
    validate_phase4_assurance_artifact(artifact)
    return artifact


def validate_phase4_assurance_artifact(artifact: Phase4AssuranceArtifact) -> None:
    """拒绝缺 family、重复/未知 family、非通过状态或 identity 被篡改的最终 artifact。"""

    if artifact.format != ASSURANCE_FORMAT or tuple(item.family for item in artifact.entries) != REQUIRED_FAMILIES:
        raise ValueError("P7 assurance family 缺失、额外、重复或乱序")
    if any(item.status != "passed" or not item.contract_version or not item.artifact_identity for item in artifact.entries):
        raise ValueError("P7 assurance 存在未通过或身份缺失的 family")
    if _hash(artifact.unsigned_payload()) != artifact.artifact_identity:
        raise ValueError("P7 assurance artifact identity 不匹配")


def render_assurance_markdown(artifact: Phase4AssuranceArtifact) -> str:
    """生成供人工检查的简短矩阵，不将 technical Gate 夸大为 Phase 4 最终验收。"""

    validate_phase4_assurance_artifact(artifact)
    lines = ["# M40 Phase 4 Technical Assurance", "", f"- format: `{artifact.format}`", f"- identity: `{artifact.artifact_identity}`", "- result: `passed`（仅技术 Gate；仍需用户人工检查与 accept-module）", "", "| family | contract | artifact | status |", "| --- | --- | --- | --- |"]
    lines.extend(f"| `{item.family}` | `{item.contract_version}` | `{item.artifact_identity}` | `{item.status}` |" for item in artifact.entries)
    lines.extend(["", "## Capability boundary", "", "- 已覆盖：SQL、RAG、Hybrid、澄清恢复、安全拒绝的 Trace/合同闭环。", "- P6：保留 verified `no_go`，没有实现或默认化 RAG Subgraph。", "- 未证明：生产认证、真实外部服务质量、开放路由与长期会话。", ""])
    return "\n".join(lines)


def _validate_m39_no_go(path: Path) -> str:
    """只读核验 M39 frozen report 的必要身份和 no-go，绝不读取/重跑其大 artifact。"""

    raw = json.loads(path.read_text(encoding="utf-8"))
    required = {"format", "audit_identity", "input_artifact_identities", "input_runtime_identities", "recommendation", "no_provider_call_count"}
    if set(raw) < required or raw["format"] != "phase4-rag-subgraph-readiness-v1":
        raise ValueError("M39 audit format 不闭合")
    if raw["recommendation"] != "no_go" or raw["no_provider_call_count"] != 0:
        raise ValueError("M39 P6 decision 不再是可验证的 strict no-go")
    if not raw["audit_identity"] or not raw["input_artifact_identities"] or not raw["input_runtime_identities"]:
        raise ValueError("M39 audit identity 不完整")
    return str(raw["audit_identity"])
