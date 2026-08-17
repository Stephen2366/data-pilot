"""M38 Hybrid Harness 合同：双 required branch、private typed Evidence 与安全停止。"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.agent import ToolCallTrace
from app.api.query import _hybrid_branch_projection
from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest, HybridPlan, RouteDecision, ToolObservation
from engine.harness.graph import HarnessRuntime, run_harness
from engine.harness.hybrid import HybridSynthesisError
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import (
    DocumentEvidencePayload,
    Evidence,
    EvidenceLedger,
    EvidenceRef,
    SQLEvidencePayload,
)


def _request() -> HarnessRequest:
    """创建同一可信 caller/run 的最小 Hybrid 请求。"""

    return HarnessRequest(
        question="查询退款原因并说明退款政策",
        run_id="m38-hybrid-run",
        caller=demo_caller(caller_id="m38", roles=("ops",)),
        active_sql_role="ops",
        force_new_pipeline=False,
    )


def _ledger(evidence: Evidence) -> EvidenceLedger:
    """构造已通过 Gate 的最小账本，模拟深 Tool 交给 controller 的私有输入。"""

    # Fixture 位于 Gate 之后；真实 Document branch 的 pre-generation authorization 由
    # `RAGAnswerFlow.prepare_for_hybrid()` 覆盖，这里不伪造一份 AuthorizationDecision。
    return EvidenceLedger(
        run_id="m38-hybrid-run", evidence=(evidence,), stages=((evidence.ref.evidence_id, "generation_visible"),)
    )


def _sql_observation(*, blocked: bool = False, unavailable: bool = False) -> ToolObservation:
    """模拟 SQL 深链，不让 Graph 测试依赖真实数据库。"""

    if blocked:
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="no_answer",
            safety_status="blocked", reason_code="sql_guard_blocked", blocked_reason="只允许 SELECT",
        )
    if unavailable:
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="external_unavailable", answer_status="no_answer",
            safety_status="passed", reason_code="llm_generation_error",
        )
    evidence = Evidence(
        ref=EvidenceRef("m38-hybrid-run", "sql-e1", "sql", "sqlite", "now", "result-1", "sql-result"),
        allowed_uses=("answer_evidence",), authorization_ref="sql-guard:passed", runtime_ref="fixture",
        payload=SQLEvidencePayload(
            guarded_sql="SELECT refund_reason, refund_count FROM refunds", columns=("refund_reason", "refund_count"),
            rows_count=1, result_fingerprint="result-1", queried_at="now", database_identity="sqlite",
            runtime_identity="fixture", safe_result_view=(("质量问题", 3),),
        ),
    )
    ledger = _ledger(evidence)
    return ToolObservation(
        tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete", safety_status="passed",
        reason_code="sql_completed", tool_calls=(ToolCallTrace(tool_name="sql_query", status="success"),),
        evidence_refs=(evidence.ref.audit_projection(),), ledger_projection=ledger.safe_projection(), evidence_ledger=ledger,
        raw_evidence=(evidence,),
    )


def _rag_observation(*, blocked: bool = False, unavailable: bool = False) -> ToolObservation:
    """模拟 RAG Gate-only branch，确保它没有可被拼接的自然语言子答案。"""

    if blocked:
        return ToolObservation(
            tool_name="rag_evidence_gate", route="rag", execution_status="completed", answer_status="no_answer",
            safety_status="blocked", reason_code="document_acl_denied", blocked_reason="文档证据未获授权。",
        )
    if unavailable:
        return ToolObservation(
            tool_name="rag_evidence_gate", route="rag", execution_status="external_unavailable", answer_status="no_answer",
            safety_status="passed", reason_code="knowledge_tool_unavailable",
        )
    evidence = Evidence(
        ref=EvidenceRef("m38-hybrid-run", "doc-e1", "document", "authority-1", "r1", "content-1", "a1"),
        allowed_uses=("answer_evidence",), authorization_ref="auth-1", runtime_ref="fixture",
        payload=DocumentEvidencePayload(
            release_identity="release-1", document_key="refund-policy", revision="r1", title="退款规则",
            knowledge_type="policy", anchor="a1", content="质量问题退款须经平台质检确认后办理。",
        ),
    )
    ledger = _ledger(evidence)
    return ToolObservation(
        tool_name="rag_evidence_gate", route="rag", execution_status="completed", answer_status="complete", safety_status="passed",
        reason_code="hybrid_document_evidence_ready", tool_calls=(ToolCallTrace(tool_name="rag_evidence_gate", status="success"),),
        evidence_refs=(evidence.ref.audit_projection(),), ledger_projection=ledger.safe_projection(), evidence_ledger=ledger,
        raw_evidence=(evidence,),
    )


@dataclass
class FakeSQLTool:
    """记录 Hybrid SQL 深 Tool 预算。"""

    observation: ToolObservation
    calls: int = 0

    def run(self, _request: HarnessRequest) -> ToolObservation:
        self.calls += 1
        return self.observation

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        return self.run(request)


@dataclass
class FakeRAGTool:
    """记录 Hybrid RAG 深 Tool 预算，并显式实现 Gate-only seam。"""

    observation: ToolObservation
    calls: int = 0

    def run(self, _request: HarnessRequest) -> ToolObservation:
        self.calls += 1
        return self.observation

    def run_for_hybrid(self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement) -> ToolObservation:
        assert requirement.required_terms == ("质量问题",)
        return self.run(request)


@dataclass
class HybridRouter:
    """返回固定薄计划，隔离 Router 词表以聚焦 Graph/controller。"""

    conflict: bool = False

    def decide(self, _request: HarnessRequest) -> RouteDecision:
        return RouteDecision(
            route="hybrid", reason_code="hybrid_plan_required", needs_evidence=True, termination_action="answer",
            hybrid_plan=HybridPlan(
                identity="m38-fixture-plan", operator="refund_reason_and_policy", sql_question="退款原因排名",
                rag_question="质量问题退款规则", requirement=AnswerEvidenceRequirement(required_terms=("质量问题",)),
                conflict_fact_key="fixture-conflict" if self.conflict else None,
            ),
        )


class UnavailableSynthesizer:
    """模拟正式 adapter 不可用，验证 controller 的零重跑安全降级。"""

    identity = "fixture-unavailable"

    def compose(self, **_kwargs: object):
        raise HybridSynthesisError("unavailable")


def _run(*, sql: ToolObservation, rag: ToolObservation, conflict: bool = False, synth: object | None = None):
    """通过原 Harness seam 执行一次 fixture Hybrid。"""

    sql_tool, rag_tool = FakeSQLTool(sql), FakeRAGTool(rag)
    result = run_harness(
        request=_request(),
        runtime=HarnessRuntime(sql_tool=sql_tool, rag_tool=rag_tool, router=HybridRouter(conflict), hybrid_synthesizer=synth),
    )
    return result, sql_tool, rag_tool


def test_hybrid_complete_requires_two_gate_visible_evidence_and_two_citations() -> None:
    """两个 required branch 都成功时才 complete，且跨来源 claim 同时绑定两种 citation。"""

    result, sql_tool, rag_tool = _run(sql=_sql_observation(), rag=_rag_observation())

    assert (result.route, result.execution_status, result.answer_status, result.safety_status) == (
        "hybrid", "completed", "complete", "passed"
    )
    assert result.graph_steps == ("route", "hybrid_sql_tool", "hybrid_rag_tool", "controller")
    assert sql_tool.calls == rag_tool.calls == 1
    assert result.hybrid is not None
    assert {item["source_kind"] for item in result.hybrid.citations} == {"sql", "document"}
    assert "质量问题退款须经" in result.answer


def test_hybrid_allows_only_independent_sql_partial_when_rag_is_unavailable() -> None:
    """required RAG 缺失不能伪装 complete；SQL partial 不引用或泄露 Document Evidence。"""

    result, sql_tool, rag_tool = _run(sql=_sql_observation(), rag=_rag_observation(unavailable=True))

    assert (result.answer_status, result.safety_status, result.reason_code) == ("partial", "passed", "hybrid_safe_partial")
    assert result.hybrid is not None
    assert {item["source_kind"] for item in result.hybrid.citations} == {"sql"}
    assert sql_tool.calls == rag_tool.calls == 1


def test_hybrid_sql_safety_stops_without_using_rag_as_a_fallback_answer() -> None:
    """SQL Guard 是硬停止；RAG 的可用规则不能把危险查询淡化成完整建议。"""

    result, _sql_tool, rag_tool = _run(sql=_sql_observation(blocked=True), rag=_rag_observation())

    assert (result.answer_status, result.safety_status, result.reason_code) == (
        "no_answer", "blocked", "hybrid_sql_safety_blocked"
    )
    assert rag_tool.calls == 1


def test_hybrid_conflict_is_stable_stop_not_silent_choice() -> None:
    """同一事实键冲突时 controller 输出固定 conflict 状态，不产生 claim/citation。"""

    result, _sql_tool, _rag_tool = _run(sql=_sql_observation(), rag=_rag_observation(), conflict=True)

    assert (result.answer_status, result.reason_code) == ("insufficient_evidence", "hybrid_evidence_conflict")
    assert result.hybrid is not None and result.hybrid.claims == () and result.hybrid.citations == ()


def test_synthesizer_failure_keeps_only_safe_partial_without_rerunning_branches() -> None:
    """adapter 异常后只用已验证 SQL Evidence 降级，两个 Tool 的次数仍恰好各一次。"""

    result, sql_tool, rag_tool = _run(
        sql=_sql_observation(), rag=_rag_observation(), synth=UnavailableSynthesizer()
    )

    assert (result.execution_status, result.answer_status, result.reason_code) == (
        "failed", "partial", "hybrid_synthesizer_partial"
    )
    assert result.hybrid is not None
    assert {item["source_kind"] for item in result.hybrid.citations} == {"sql"}
    assert sql_tool.calls == rag_tool.calls == 1


def test_denied_rag_branch_has_no_public_side_channel_in_sql_partial_projection() -> None:
    """ACL 拒绝后只发布 SQL 独立事实；branch 摘要不含文档 ref 或真实拒绝原因。"""

    result, _sql_tool, _rag_tool = _run(sql=_sql_observation(), rag=_rag_observation(blocked=True))

    assert (result.answer_status, result.safety_status) == ("partial", "passed")
    projected = _hybrid_branch_projection(result)
    rag = next(item for item in projected if item["branch"] == "rag")
    assert rag["reason_code"] == "branch_not_disclosed"
    assert rag["evidence_refs"] == []
