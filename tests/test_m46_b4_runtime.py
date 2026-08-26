"""M46-C：B4 business 子图在真实 task/API seam 内仍只消耗一次父级 Knowledge action。"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from engine.harness.adapters import RAGToolAdapter
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.phase4b.rag_subgraph import (
    BoundedRAGSubgraphAcquirer,
    BusinessT4SlotProvider,
    ChildAttempt,
    ChildConsumption,
    ChildLedger,
    RAGSubgraphContractError,
    _recovery_first_sources,
)
from engine.phase4b.task_boundary import TaskBoundary
from engine.rag.answer_flow import RAGAnswerFlow
from engine.rag.evidence import EvidenceLedger, make_sql_evidence
from engine.rag.evidence_acquisition import PipelineEvidenceAcquirer
from engine.rag.knowledge_tool import KnowledgeTool
from engine.rag.release import load_active_release


class _DeterministicSQLTool:
    """P1 的 SQL fixture：仅证明 product task 的混合父 Loop，不访问真实数据库。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        evidence = make_sql_evidence(
            run_id=request.run_id, guarded_sql="SELECT m46_fixture", columns=("reason", "increment"),
            rows_count=1, result_fingerprint="m46-p1", queried_at="now", database_identity="fixture",
            runtime_identity="m46-deterministic-sql-v1", safe_result_view=(("质量问题", 48000),),
        )
        ledger = EvidenceLedger(request.run_id, (evidence,), ((evidence.ref.evidence_id, "generation_visible"),))
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer="SQL 证据已取得。",
            sql="SELECT m46_fixture", columns=("reason", "increment"), rows=({"reason": "质量问题", "increment": 48000},),
            evidence_refs=(evidence.ref.audit_projection(),), evidence_ledger=ledger,
            ledger_projection=ledger.safe_projection(), raw_evidence=(evidence,),
        )

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        return self.run(request)


def _b4_business_rag_tool() -> RAGToolAdapter:
    """使用真实 active business release；测试不伪造 policy 文档或 ACL。"""

    knowledge = KnowledgeTool()
    acquirer = BoundedRAGSubgraphAcquirer(
        initial_acquirer=PipelineEvidenceAcquirer(knowledge_tool=knowledge, active_loader=load_active_release),
        knowledge_tool=knowledge,
        active_loader=load_active_release,
        slot_provider=BusinessT4SlotProvider(),
        runtime_scope="business_release",
    )
    return RAGToolAdapter(
        answer_flow=RAGAnswerFlow(
            knowledge_tool=knowledge, active_loader=load_active_release, evidence_acquirer=acquirer,
        ),
        knowledge_runtime_kind="business_release",
    )


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    def override_db() -> Generator[Session, None, None]:
        with Session(database) as session:
            yield session

    previous = (
        app.state.caller_resolver, app.state.sql_tool_factory, app.state.task_boundary,
        app.state.business_rag_tool_factory, app.state.b4_task_enabled,
    )
    app.dependency_overrides[get_db] = override_db
    app.state.trace_path = trace_path
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    app.state.sql_tool_factory = _DeterministicSQLTool
    app.state.business_rag_tool_factory = _b4_business_rag_tool
    app.state.task_boundary = TaskBoundary()
    app.state.b4_task_enabled = True
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        (
            app.state.caller_resolver, app.state.sql_tool_factory, app.state.task_boundary,
            app.state.business_rag_tool_factory, app.state.b4_task_enabled,
        ) = previous


def test_b4_business_subgraph_is_one_parent_action_with_safe_child_timeline(tmp_path: Path) -> None:
    """B4 能补齐两篇 policy，且 API/Trace 只看见父动作与脱敏 child ledger。"""

    trace_path = tmp_path / "m46-p1-rehearsal.jsonl"
    with _client(trace_path) as client:
        response = client.post("/api/query", json={
            "question": "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。",
            "task": {"action": "start"},
        })
    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())

    assert response.status_code == 200
    assert body["runtime_family"] == "agent_task"
    assert body["agent_loop_runtime"]["b4_enabled"] is True
    assert body["agent_budget"]["consumed"]["knowledge_actions"] == 1
    assert body["agent_budget"]["consumed"]["retrieval_batches"] <= 3
    document_attempt = next(item for item in body["action_attempts"] if item["action_id"] == "collect_document_evidence")
    child = document_attempt["observation"]["diagnostics"]["b4_subgraph"]
    assert child["termination"] == "answer_ready"
    assert child["consumption"]["initial_retrieval_batches"] == 1
    assert 1 <= len(child["attempts"]) <= 2
    # Task/API 是公开安全投影，EvidenceRef 不公开 document key。required-key coverage 由
    # Shared Gate 的 complete 事实证明；子图可合法保留第三篇辅助 Evidence，不能将其硬截成两篇。
    assert body["answer_status"] == "complete"
    assert 2 <= child["consumption"]["selected"] <= 3
    assert len([item for item in body["task"]["state"]["evidence"] if item["route"] == "document"]) == child["consumption"]["selected"]
    # M47 后 Trace 顶层是 B5 durable envelope，父 Loop 仍保留自己的 B4 identity。
    assert trace["runtime_identity"]["predecessor_contract_identity"] == body["agent_loop_runtime"]["contract_identity"]
    assert trace["runtime_identity"]["predecessor_contract_identity"]
    assert "question" not in json.dumps(child, ensure_ascii=False).lower()


def test_final_selection_prioritizes_latest_recovery_before_initial() -> None:
    """initial 已占满上限时，第二步新增 Evidence 也不能在最终截断前消失。"""

    class _Initial:
        selected_evidence = ("initial-1", "initial-2", "initial-3")

    class _Execution:
        def __init__(self, *added: str) -> None:
            self.added_evidence = added

    ordered = _recovery_first_sources(  # type: ignore[arg-type] - 纯顺序函数的最小 sentinel。
        initial=_Initial(),
        executions=(_Execution("rewrite-1"), _Execution("expansion-1", "expansion-2")),
    )

    assert ordered[:3] == ("expansion-1", "expansion-2", "rewrite-1")
    assert ordered[3:] == ("initial-1", "initial-2", "initial-3")


def test_child_budget_keeps_retrieval_and_expansion_candidate_accounts_separate() -> None:
    """合法 expansion 不挤占 retrieval 15-candidate 账，但仍受自己的 2×8/新增4条上限。"""

    base = ChildLedger(consumption=ChildConsumption(
        initial_retrieval_batches=1,
        rewrite_retrieval_batches=2,
        candidates_examined=15,
    ))
    legal = ChildAttempt(
        ordinal=1,
        action="context_expansion_candidate",
        status="completed",
        eligible_actions=("context_expansion_candidate", "stop"),
        rejected_actions=("query_rewrite_candidate",),
        evidence_added=4,
        duplicate_count=0,
        consumption=ChildConsumption(
            expansion_candidates_scanned=16,
            expansion_evidence_added=4,
            unique_merged_evidence=4,
        ),
        progress_reason="evidence_gain",
    )
    assert base.with_attempt(legal).consumption.candidates_examined == 15

    with pytest.raises(RAGSubgraphContractError, match="child_budget_exhausted"):
        base.with_attempt(replace(
            legal,
            consumption=replace(legal.consumption, expansion_candidates_scanned=17),
        ))
