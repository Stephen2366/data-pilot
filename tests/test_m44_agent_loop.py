"""M44 B2：Observation-driven Loop、runtime resolver 与 bounded repair。"""

from __future__ import annotations

from dataclasses import dataclass

from engine.governance import demo_caller
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.phase4b.agent_loop import AgentLoopRuntime, run_agent_loop
import engine.phase4b.agent_loop as agent_loop_module
from engine.phase4b.knowledge_runtime import KnowledgeRuntimeResolver, KnowledgeRuntimeSpec
from engine.phase4b.task_runtime import apply_delta, understand_turn
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import (
    DocumentEvidencePayload,
    Evidence,
    EvidenceLedger,
    EvidenceRef,
    make_sql_evidence,
)


def _request(question: str, run_id: str = "m44-loop") -> HarnessRequest:
    return HarnessRequest(
        question=question,
        run_id=run_id,
        caller=demo_caller(caller_id="m44", roles=("ops",)),
        active_sql_role="ops",
        force_new_pipeline=True,
    )


def _ledger(run_id: str, evidence: tuple[Evidence, ...]) -> EvidenceLedger:
    if evidence and evidence[0].ref.evidence_kind == "document":
        # fixture 位于真实 RAG pre-generation Gate 之后，不在 Loop test 重演 ACL。
        return EvidenceLedger(
            run_id=run_id,
            evidence=evidence,
            stages=tuple((item.ref.evidence_id, "generation_visible") for item in evidence),
        )
    ledger = EvidenceLedger.from_candidates(run_id=run_id, evidence=evidence)
    ids = tuple(item.ref.evidence_id for item in evidence)
    return ledger.transition(evidence_ids=ids, to_stage="selected").transition(
        evidence_ids=ids, to_stage="generation_visible"
    )


def _sql_observation(request: HarnessRequest, *, rows: tuple[dict[str, object], ...], sql: str = "SELECT 1") -> ToolObservation:
    evidence = make_sql_evidence(
        run_id=request.run_id,
        guarded_sql=sql,
        columns=tuple(rows[0]) if rows else ("value",),
        rows_count=len(rows),
        result_fingerprint=f"fp-{len(rows)}-{request.question}",
        queried_at="2026-08-24T00:00:00Z",
        database_identity="fixture-db",
        runtime_identity="m44-sql-fixture-v1",
        safe_result_view=tuple(tuple(row.values()) for row in rows),
    )
    ledger = _ledger(request.run_id, (evidence,))
    return ToolObservation(
        tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
        safety_status="passed", reason_code="sql_completed", answer=f"SQL:{request.question}", sql=sql,
        columns=tuple(rows[0]) if rows else (), rows=rows,
        evidence_refs=(evidence.ref.audit_projection(),), ledger_projection=ledger.safe_projection(),
        evidence_ledger=ledger, raw_evidence=(evidence,),
    )


def _dialect_failure() -> ToolObservation:
    return ToolObservation(
        tool_name="text2sql", route="sql", execution_status="failed", answer_status="no_answer",
        safety_status="passed", reason_code="sql_dialect_incompatible",
        sql="SELECT DATE_TRUNC('month', paid_at) FROM refunds",
        error_type="sql_execution_error", diagnostics={"issue_code": "mysql_unsupported_date_trunc"},
    )


def _document_observation(run_id: str, *, both: bool = True) -> ToolObservation:
    keys = ("refund_policy_basic", "refund_policy_quality") if both else ("refund_policy_quality",)
    evidence = tuple(
        Evidence(
            ref=EvidenceRef(run_id, f"doc-{key}", "document", "authority", "r1", f"content-{key}", key),
            allowed_uses=("answer_evidence",), authorization_ref="auth", runtime_ref="business-release",
            payload=DocumentEvidencePayload(
                "release-1", key, "r1", key, "policy", key, f"{key} 的受控政策正文。"
            ),
        )
        for key in keys
    )
    ledger = _ledger(run_id, evidence)
    return ToolObservation(
        tool_name="rag_evidence_gate", route="rag", execution_status="completed", answer_status="complete",
        safety_status="passed", reason_code="hybrid_document_evidence_ready",
        evidence_refs=tuple(item.ref.audit_projection() for item in evidence),
        ledger_projection=ledger.safe_projection(), evidence_ledger=ledger, raw_evidence=evidence,
        diagnostics={"candidate_count": len(evidence), "selected_count": len(evidence),
                     "context_count": len(evidence), "knowledge_runtime_kind": "business_release"},
    )


@dataclass
class ProductSQLTool:
    quality_positive: bool = True
    dialect_first: bool = False
    calls: int = 0
    repair_calls: int = 0
    reason_increment_seen: int | None = None

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        self.calls += 1
        if self.dialect_first and self.calls == 1:
            return _dialect_failure()
        if "退款原因" in request.question:
            increment = 48000 if self.quality_positive else -100
            self.reason_increment_seen = increment
            return _sql_observation(request, rows=({"reason": "质量问题", "increment": increment},))
        if "商品 SKU" in request.question:
            return _sql_observation(request, rows=(
                {"sku": "SKU-HIGH-REFUND-01", "increment": 24000},
                {"sku": "SKU-WL-EB-002", "increment": 18000},
                {"sku": "SKU-SD-LP-003", "increment": 6000},
                {"sku": "SKU-MK-K2-004", "increment": 6000},
                {"sku": "SKU-MS-PL-005", "increment": 6000},
            ))
        return _sql_observation(request, rows=({"period": "2026-08", "net_refund_amount": 180000},))

    def run(self, request: HarnessRequest) -> ToolObservation:
        return self.run_for_hybrid(request)

    def run_repair(self, request: HarnessRequest, *, candidate_sql: str, issue_code: str) -> ToolObservation:
        self.repair_calls += 1
        assert "DATE_TRUNC" in candidate_sql and issue_code == "mysql_unsupported_date_trunc"
        return _sql_observation(request, rows=({"period": "2026-08", "net_refund_amount": 180000},))


@dataclass
class BusinessRAGTool:
    both: bool = True
    calls: int = 0

    def run_for_hybrid(self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement) -> ToolObservation:
        self.calls += 1
        assert requirement.required_document_keys == ("refund_policy_basic", "refund_policy_quality")
        return _document_observation(request.run_id, both=self.both)

    def run(self, request: HarnessRequest) -> ToolObservation:
        return self.run_for_hybrid(request, requirement=AnswerEvidenceRequirement())


@dataclass
class FailureSQLTool:
    observation: ToolObservation
    calls: int = 0
    repair_calls: int = 0

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        self.calls += 1
        return self.observation

    def run(self, request: HarnessRequest) -> ToolObservation:
        return self.run_for_hybrid(request)

    def run_repair(self, request: HarnessRequest, *, candidate_sql: str, issue_code: str) -> ToolObservation:
        self.repair_calls += 1
        raise AssertionError("非 allowlisted failure 不得进入 repair")


class NoEvidenceSQLTool:
    calls = 0

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        self.calls += 1
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="no_answer",
            safety_status="passed", reason_code="sql_completed_without_evidence",
        )

    def run(self, request: HarnessRequest) -> ToolObservation:
        return self.run_for_hybrid(request)


def _state(question: str):
    delta = understand_turn(question, action="start", previous=None)
    return apply_delta(None, delta, owner_ref="owner:m44")[0]


def _runtime(sql: ProductSQLTool, rag: BusinessRAGTool | None = None) -> AgentLoopRuntime:
    specs = () if rag is None else (
        KnowledgeRuntimeSpec("business_release", lambda: rag, "business-release-fixture-v1"),
    )
    return AgentLoopRuntime(sql, KnowledgeRuntimeResolver(specs))


def test_t3_second_product_action_depends_on_positive_quality_observation() -> None:
    question = "2026 年 7 月和 8 月质量问题对净退款增长贡献了多少？哪些商品最突出？"
    positive = ProductSQLTool(quality_positive=True)
    result = run_agent_loop(request=_request(question), state=_state(question), runtime=_runtime(positive))
    assert [item.action_id for item in result.attempts] == ["collect_sql_evidence", "collect_sql_evidence"]
    assert positive.calls == 2 and result.termination.reason == "answer_ready"
    assert positive.reason_increment_seen == 48000
    # Phase 4B oracle：质量问题增量 48,000；商品总增量与 7/8 月净退款总增量 60,000 对账。
    assert result.result.observation is not None
    assert sum(int(row["increment"]) for row in result.result.observation.rows) == 60000
    assert result.result.observation.rows[0]["sku"] == "SKU-HIGH-REFUND-01"

    negative = ProductSQLTool(quality_positive=False)
    stopped = run_agent_loop(request=_request(question, "m44-negative"), state=_state(question), runtime=_runtime(negative))
    assert negative.calls == 1 and stopped.termination.reason == "answer_ready"
    assert len(stopped.attempts) == 1


def test_t3_after_existing_t2_evidence_does_not_repeat_old_requirement() -> None:
    t2_question = "查询 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。"
    t2_state = _state(t2_question)
    t2 = run_agent_loop(
        request=_request(t2_question, "m44-t2"), state=t2_state,
        runtime=_runtime(ProductSQLTool()),
    )
    t3_question = "质量问题对净退款增长贡献了多少？哪些商品最突出？"
    delta = understand_turn(t3_question, action="continue", previous=t2.state)
    t3_state = apply_delta(t2.state, delta, owner_ref="owner:m44")[0]
    sql = ProductSQLTool()
    t3 = run_agent_loop(
        request=_request(t3_question, "m44-t3-after-t2"), state=t3_state, runtime=_runtime(sql)
    )
    assert sql.calls == 2
    assert [item.requirement_identity for item in t3.attempts] == [
        "sql:refund_reason:quality_issue:2026-07,2026-08",
        "sql:product_sku:quality_issue:2026-07,2026-08",
    ]


def test_only_allowlisted_dialect_failure_gets_one_repair() -> None:
    question = "查询 2026 年 8 月实际净退款金额。"
    sql = ProductSQLTool(dialect_first=True)
    result = run_agent_loop(request=_request(question), state=_state(question), runtime=_runtime(sql))
    assert [item.action_id for item in result.attempts] == ["collect_sql_evidence", "repair_sql_evidence"]
    assert sql.calls == sql.repair_calls == 1
    assert result.budget.consumed.repairs == 1 and result.termination.reason == "answer_ready"


def test_timeout_generic_failure_and_guard_deny_never_repair() -> None:
    question = "查询 2026 年 8 月实际净退款金额。"
    observations = (
        ToolObservation(
            tool_name="text2sql", route="sql", execution_status="external_unavailable",
            answer_status="no_answer", safety_status="passed", reason_code="timeout", error_type="timeout",
        ),
        ToolObservation(
            tool_name="text2sql", route="sql", execution_status="failed",
            answer_status="no_answer", safety_status="passed", reason_code="sql_execution_error",
            error_type="sql_execution_error",
        ),
        ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed",
            answer_status="no_answer", safety_status="blocked", reason_code="sql_guard_blocked",
            error_type="sql_guard_blocked", blocked_reason="blocked",
        ),
    )
    for index, observation in enumerate(observations):
        sql = FailureSQLTool(observation)
        result = run_agent_loop(
            request=_request(question, f"m44-no-repair-{index}"), state=_state(question),
            runtime=AgentLoopRuntime(sql, KnowledgeRuntimeResolver(())),
        )
        assert sql.calls == 1 and sql.repair_calls == 0
        assert len(result.attempts) == 1


def test_no_evidence_gain_stops_and_actual_overrun_remains_in_ledger() -> None:
    question = "查询 2026 年 8 月实际净退款金额。"
    empty = NoEvidenceSQLTool()
    stopped = run_agent_loop(
        request=_request(question, "m44-no-progress"), state=_state(question),
        runtime=AgentLoopRuntime(empty, KnowledgeRuntimeResolver(())),
    )
    assert empty.calls == 1 and stopped.termination.reason == "no_progress"
    assert stopped.attempts[0].progress.coverage_increased is False

    class OverBudgetRAG(BusinessRAGTool):
        def run_for_hybrid(
            self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement
        ) -> ToolObservation:
            observed = super().run_for_hybrid(request, requirement=requirement)
            return ToolObservation(**{
                **observed.__dict__,
                "diagnostics": {**observed.diagnostics, "candidate_count": 6},
            })

    hybrid_question = "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。"
    overrun = run_agent_loop(
        request=_request(hybrid_question, "m44-overrun"), state=_state(hybrid_question),
        runtime=_runtime(ProductSQLTool(), OverBudgetRAG()),
    )
    assert overrun.termination.reason == "budget_exhausted"
    assert overrun.termination.detail_code == "actual_consumption_exceeded"
    assert len(overrun.attempts) == 2 and overrun.budget.consumed.candidates == 6


def test_t4_uses_business_runtime_and_missing_required_doc_stops_partial() -> None:
    question = "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。"
    sql, rag = ProductSQLTool(), BusinessRAGTool(both=True)
    complete = run_agent_loop(request=_request(question), state=_state(question), runtime=_runtime(sql, rag))
    assert [item.action_id for item in complete.attempts] == ["collect_sql_evidence", "collect_document_evidence"]
    assert complete.termination.reason == "answer_ready" and complete.result.answer_status == "complete"
    assert complete.knowledge_runtimes == ({"scope": "business_release", "runtime_identity": "business-release-fixture-v1"},)

    partial_rag = BusinessRAGTool(both=False)
    partial = run_agent_loop(
        request=_request(question, "m44-partial"), state=_state(question),
        runtime=_runtime(ProductSQLTool(), partial_rag),
    )
    assert partial_rag.calls == 1
    assert partial.termination.reason == "budget_exhausted"
    assert partial.result.answer_status in {"partial", "insufficient_evidence"}


def test_graph_contract_exception_fails_closed_without_partial_answer(monkeypatch) -> None:
    class BrokenGraph:
        def invoke(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("recursion_or_contract_failure")

    monkeypatch.setattr(agent_loop_module, "DEFAULT_AGENT_LOOP", BrokenGraph())
    question = "查询 2026 年 8 月实际净退款金额。"
    result = run_agent_loop(
        request=_request(question, "m44-broken-graph"), state=_state(question),
        runtime=_runtime(ProductSQLTool()),
    )
    assert result.termination.reason == "agent_loop_contract_failure"
    assert result.attempts == () and result.result.answer_status == "no_answer"
