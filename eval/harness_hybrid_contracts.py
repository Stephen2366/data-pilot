"""M38 独立 Hybrid contract Eval：每题一次 Harness 运行，多断言复用同一 execution 事实。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal

from app.schemas.agent import ToolCallTrace
from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest, HybridPlan, RouteDecision, ToolObservation
from engine.harness.graph import HarnessRuntime, run_harness
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import DocumentEvidencePayload, Evidence, EvidenceLedger, EvidenceRef, SQLEvidencePayload

HYBRID_CONTRACT_VERSION = "phase4-harness-hybrid-v1"
ASSERTION_IDS = ("route_plan", "branch_budget", "required_status", "citation_binding", "safe_terminal")


@dataclass(frozen=True)
class HybridScenario:
    """闭集 scenario，覆盖 complete、partial、ACL/safety 类停止与 conflict。"""

    scenario_id: str
    kind: Literal["complete", "sql_partial", "rag_partial", "sql_blocked", "conflict"]


SCENARIOS = (
    HybridScenario("refund_reason_and_policy", "complete"),
    HybridScenario("sql_only_partial", "sql_partial"),
    HybridScenario("rag_only_partial", "rag_partial"),
    HybridScenario("sql_guard_stop", "sql_blocked"),
    HybridScenario("structured_conflict", "conflict"),
)


@dataclass(frozen=True)
class HybridExecutionEvidence:
    """安全 execution 投影，不保留正文、完整 rows 或 RAG deny 细节。"""

    scenario_id: str
    invocation_count: int
    route: str
    execution_status: str
    answer_status: str
    safety_status: str
    sql_calls: int
    rag_calls: int
    citation_kinds: tuple[str, ...]
    graph_steps: tuple[str, ...]


@dataclass(frozen=True)
class HybridAssertion:
    """一条 typed Eval 判断。"""

    scenario_id: str
    assertion_id: str
    status: Literal["passed", "failed"]


@dataclass(frozen=True)
class HybridArtifact:
    """closed-world artifact，拒绝漏 scenario、重跑或遗漏 assertion。"""

    contract_version: str
    selected_scenario_ids: tuple[str, ...]
    execution_evidence: tuple[HybridExecutionEvidence, ...]
    assertions: tuple[HybridAssertion, ...]
    artifact_identity: str


def _ready(evidence: Evidence) -> EvidenceLedger:
    """Eval fake 模拟已经过深 Tool 授权/Gate 的私有 Evidence，不测试重复的 RAG internals。"""

    return EvidenceLedger("hybrid-eval", (evidence,), ((evidence.ref.evidence_id, "generation_visible"),))


def _sql(kind: str) -> ToolObservation:
    """构造 SQL branch 的成功/技术失败/安全拦截形状。"""

    if kind == "sql_blocked":
        return ToolObservation("text2sql", "sql", "completed", "no_answer", "blocked", "sql_guard_blocked", blocked_reason="guard")
    if kind == "rag_partial":
        return ToolObservation("text2sql", "sql", "external_unavailable", "no_answer", "passed", "sql_unavailable")
    evidence = Evidence(
        EvidenceRef("hybrid-eval", "sql", "sql", "eval-db", "now", "sql-result", "sql-result"),
        ("answer_evidence",), "sql-guard:passed", "eval",
        SQLEvidencePayload("SELECT 1", ("refund_count",), 1, "sql-result", "now", "eval-db", "eval", ((3,),)),
    )
    ledger = _ready(evidence)
    return ToolObservation(
        "text2sql", "sql", "completed", "complete", "passed", "sql_completed",
        tool_calls=(ToolCallTrace(tool_name="sql", status="success"),), evidence_refs=(evidence.ref.audit_projection(),),
        ledger_projection=ledger.safe_projection(), evidence_ledger=ledger, raw_evidence=(evidence,),
    )


def _rag(kind: str) -> ToolObservation:
    """构造 Gate-only RAG branch；不创建自然语言子答案字段。"""

    if kind == "sql_partial":
        return ToolObservation("rag_evidence_gate", "rag", "external_unavailable", "no_answer", "passed", "rag_unavailable")
    evidence = Evidence(
        EvidenceRef("hybrid-eval", "document", "document", "authority", "r1", "content", "a1"),
        ("answer_evidence",), "auth", "eval",
        DocumentEvidencePayload("release", "refund", "r1", "退款规则", "policy", "a1", "质量问题退款须经确认。"),
    )
    ledger = _ready(evidence)
    return ToolObservation(
        "rag_evidence_gate", "rag", "completed", "complete", "passed", "hybrid_document_evidence_ready",
        tool_calls=(ToolCallTrace(tool_name="rag", status="success"),), evidence_refs=(evidence.ref.audit_projection(),),
        ledger_projection=ledger.safe_projection(), evidence_ledger=ledger, raw_evidence=(evidence,),
    )


class _SQLTool:
    """Eval 计数 SQL adapter。"""

    def __init__(self, kind: str) -> None:
        self.kind, self.calls = kind, 0

    def run(self, request: HarnessRequest) -> ToolObservation:
        self.calls += 1
        return _sql(self.kind)

    run_for_hybrid = run


class _RAGTool:
    """Eval 计数 RAG adapter。"""

    def __init__(self, kind: str) -> None:
        self.kind, self.calls = kind, 0

    def run(self, request: HarnessRequest) -> ToolObservation:
        self.calls += 1
        return _rag(self.kind)

    def run_for_hybrid(self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement) -> ToolObservation:
        return self.run(request)


class _Router:
    """每个 Eval scenario 固定一份薄计划，conflict 只由结构化 fact key 触发。"""

    def __init__(self, kind: str) -> None:
        self.kind = kind

    def decide(self, request: HarnessRequest) -> RouteDecision:
        return RouteDecision(
            "hybrid", "hybrid_plan_required", True, "answer",
            hybrid_plan=HybridPlan(
                "hybrid-eval-plan", "refund_reason_and_policy", "退款原因排名", "质量问题退款规则",
                AnswerEvidenceRequirement(required_terms=("质量问题",)), conflict_fact_key="same-fact" if self.kind == "conflict" else None,
            ),
        )


def run_hybrid_contracts(*, scenarios: tuple[HybridScenario, ...] = SCENARIOS) -> HybridArtifact:
    """每个 Scenario 恰好运行一次 Graph，并以同一 result 投影所有 required assertions。"""

    executions: list[HybridExecutionEvidence] = []
    assertions: list[HybridAssertion] = []
    for scenario in scenarios:
        sql, rag = _SQLTool(scenario.kind), _RAGTool(scenario.kind)
        result = run_harness(
            request=HarnessRequest(
                "Hybrid Eval", f"hybrid-eval-{scenario.scenario_id}",
                demo_caller(caller_id="eval", roles=("ops",)), "ops",
            ),
            runtime=HarnessRuntime(sql_tool=sql, rag_tool=rag, router=_Router(scenario.kind)),
        )
        citations = result.hybrid.citations if result.hybrid else ()
        evidence = HybridExecutionEvidence(
            scenario.scenario_id, 1, result.route, result.execution_status, result.answer_status, result.safety_status,
            sql.calls, rag.calls, tuple(sorted(item["source_kind"] for item in citations)), result.graph_steps,
        )
        executions.append(evidence)
        expected_status = {"complete": "complete", "sql_partial": "partial", "rag_partial": "partial", "sql_blocked": "no_answer", "conflict": "insufficient_evidence"}[scenario.kind]
        expected_safety = "blocked" if scenario.kind == "sql_blocked" else "passed"
        assertions.extend((
            HybridAssertion(scenario.scenario_id, "route_plan", "passed" if result.route == "hybrid" else "failed"),
            HybridAssertion(scenario.scenario_id, "branch_budget", "passed" if (sql.calls, rag.calls) == (1, 1) else "failed"),
            HybridAssertion(scenario.scenario_id, "required_status", "passed" if (result.answer_status, result.safety_status) == (expected_status, expected_safety) else "failed"),
            HybridAssertion(scenario.scenario_id, "citation_binding", "passed" if _citation_ok(scenario.kind, evidence.citation_kinds) else "failed"),
            HybridAssertion(scenario.scenario_id, "safe_terminal", "passed" if result.graph_steps[-1:] == ("controller",) else "failed"),
        ))
    unsigned = {"contract_version": HYBRID_CONTRACT_VERSION, "selected_scenario_ids": [item.scenario_id for item in scenarios], "execution_evidence": [asdict(item) for item in executions], "assertions": [asdict(item) for item in assertions]}
    artifact = HybridArtifact(HYBRID_CONTRACT_VERSION, tuple(item.scenario_id for item in scenarios), tuple(executions), tuple(assertions), sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
    validate_completed_hybrid_artifact(artifact, scenarios=scenarios)
    return artifact


def _citation_ok(kind: str, kinds: tuple[str, ...]) -> bool:
    """跨来源完整回答必须双绑定；partial 只能带其独立来源；停止没有 citation。"""

    return {"complete": kinds == ("document", "sql"), "sql_partial": kinds == ("sql",), "rag_partial": kinds == ("document",), "sql_blocked": not kinds, "conflict": not kinds}[kind]


def validate_completed_hybrid_artifact(artifact: HybridArtifact, *, scenarios: tuple[HybridScenario, ...] = SCENARIOS) -> None:
    """拒绝 scenario、执行或 assertion 不闭合的 artifact。"""

    ids = tuple(item.scenario_id for item in scenarios)
    if artifact.contract_version != HYBRID_CONTRACT_VERSION or artifact.selected_scenario_ids != ids:
        raise ValueError("Hybrid artifact contract/scenario 不匹配")
    if tuple(item.scenario_id for item in artifact.execution_evidence) != ids or any(item.invocation_count != 1 for item in artifact.execution_evidence):
        raise ValueError("每个 Hybrid scenario 必须恰好一次 Graph execution")
    expected = [(scenario_id, assertion_id) for scenario_id in ids for assertion_id in ASSERTION_IDS]
    if [(item.scenario_id, item.assertion_id) for item in artifact.assertions] != expected or any(item.status != "passed" for item in artifact.assertions):
        raise ValueError("Hybrid assertions 缺失、重复或失败")
