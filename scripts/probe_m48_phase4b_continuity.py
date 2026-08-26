"""M48-P2：真实 MySQL + business Subgraph 的跨进程连续 Task 探针。

本脚本只允许连接 ``datapilot_m48_test``。父进程负责迁移、Phase 4B seed、启动两个
独立 worker 与最终 synthetic task 清理；worker A/B 分别模拟服务重启前后，避免把
“重新创建 TestClient”误当作 durable restart 证据。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import create_app
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.harness.adapters import RAGToolAdapter
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.phase4b.mysql_task_boundary import MySQLTaskBoundary
from engine.phase4b.rag_subgraph import BoundedRAGSubgraphAcquirer, BusinessT4SlotProvider
from engine.phase4b.task_context import TaskContextCodec, TaskContextWindow
from engine.rag.answer_flow import RAGAnswerFlow
from engine.rag.evidence import EvidenceLedger, make_sql_evidence
from engine.rag.evidence_acquisition import PipelineEvidenceAcquirer
from engine.rag.knowledge_tool import KnowledgeTool
from engine.rag.release import load_active_release
from engine.sql_guard.guard import validate_readonly_sql

TARGET_DATABASE = "datapilot_m48_test"
HEAD = "20260827_0005"
OUTPUT = Path(".agent_work/temp/m48/probe-p2")
QUESTIONS = (
    "查询 2026 年 7 月实际净退款金额。",
    "比较 2026 年 7 月和 8 月实际净退款金额。",
    "2026 年 7 月和 8 月质量问题对净退款增长贡献了多少？哪些商品最突出？",
    "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。",
    "更正为按渠道比较 2026 年 7 月和 8 月，并重新核验退款政策。",
    "解释这个结果。",
    "更正：继续按渠道比较 2026 年 7 月和 8 月，并解释质量问题全额退款的前提和材料。",
)


def _json(path: Path, value: Any) -> None:
    """所有一次性证据集中写入模块临时目录。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Phase4BOracleSQL:
    """走真实 SQL Guard 的 frozen QueryPlan oracle；不调用 LLM，也不执行生成 SQL。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        """按 B2 已冻结 requirement 选择 oracle rows，并形成正式 SQL Evidence。"""

        guarded_sql = "SELECT 'phase4b' AS deterministic_oracle"
        assert validate_readonly_sql(guarded_sql).is_allowed
        if "退款原因" in request.question:
            rows = ({"reason": "质量问题", "increment": 48000},)
        elif "商品 SKU" in request.question:
            rows = (
                {"sku": "SKU-HIGH-REFUND-01", "increment": 24000},
                {"sku": "SKU-WL-EB-002", "increment": 18000},
                {"sku": "SKU-SD-LP-003", "increment": 6000},
                {"sku": "SKU-MK-K2-004", "increment": 6000},
                {"sku": "SKU-MS-PL-005", "increment": 6000},
            )
        elif "按渠道" in request.question:
            rows = (
                {"channel": "Mobile App", "increment": 30000},
                {"channel": "other", "increment": 30000},
            )
        else:
            rows = (
                {"period": "2026-07", "value": 120000},
                {"period": "2026-08", "value": 180000},
            )
        columns = tuple(rows[0])
        evidence = make_sql_evidence(
            run_id=request.run_id, guarded_sql=guarded_sql, columns=columns,
            rows_count=len(rows), result_fingerprint=f"m48-oracle:{request.run_id}:{len(rows)}",
            queried_at="frozen-phase4b-seed", database_identity=TARGET_DATABASE,
            runtime_identity="phase4b-deterministic-query-plan-oracle-v1",
            safe_result_view=tuple(tuple(row.values()) for row in rows),
        )
        ledger = EvidenceLedger(
            request.run_id, (evidence,), ((evidence.ref.evidence_id, "generation_visible"),)
        )
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed",
            answer_status="complete", safety_status="passed", reason_code="sql_completed",
            answer="已取得 Phase 4B 冻结 SQL oracle。", sql=guarded_sql,
            columns=columns, rows=rows, tables_used=("refunds",),
            evidence_refs=(evidence.ref.audit_projection(),), raw_evidence=(evidence,),
            evidence_ledger=ledger, ledger_projection=ledger.safe_projection(),
            diagnostics={
                "query_plan_identity": "phase4b-deterministic-query-plan-v1",
                "sql_guard": "passed", "database_identity": TARGET_DATABASE,
            },
        )

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        return self.run(request)


def _business_subgraph() -> RAGToolAdapter:
    """复用产品 business release 与 B4 有界 Subgraph，不接 Milvus/外部 provider。"""

    knowledge = KnowledgeTool()
    acquirer = BoundedRAGSubgraphAcquirer(
        initial_acquirer=PipelineEvidenceAcquirer(
            knowledge_tool=knowledge, active_loader=load_active_release,
        ),
        knowledge_tool=knowledge, active_loader=load_active_release,
        slot_provider=BusinessT4SlotProvider(), runtime_scope="business_release",
    )
    return RAGToolAdapter(
        answer_flow=RAGAnswerFlow(
            knowledge_tool=knowledge, active_loader=load_active_release,
            evidence_acquirer=acquirer,
        ),
        knowledge_runtime_kind="business_release",
    )


def _application(database_url: str, trace_path: Path):
    """每个 worker 独立组装 app；共享事实只有 MySQL checkpoint。"""

    app = create_app(Settings(
        _env_file=None, APP_ENV="test", DATABASE_URL=database_url,
        TASK_BOUNDARY_BACKEND="mysql", PHASE4B_RAG_STRATEGY="subgraph",
        DASHSCOPE_API_KEY="", LANGFUSE_ENABLED=False,
    ))
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    app.state.sql_tool_factory = Phase4BOracleSQL
    app.state.business_rag_tool_factory = _business_subgraph
    app.state.business_rag_runtime_identity = "business-release:m48-p2-active"
    app.state.b4_task_enabled = True
    app.state.trace_path = trace_path
    return app


def _turn(client: TestClient, question: str, previous: dict[str, Any] | None = None, *, role: str = "ops") -> dict[str, Any]:
    """发起一个严格 task envelope turn。"""

    task = {"action": "start"} if previous is None else {
        "action": "continue", "task_id": previous["task"]["task_id"],
        "expected_version": previous["task"]["task_version"],
    }
    response = client.post("/api/query", json={"question": question, "user_role": role, "task": task})
    assert response.status_code == 200, response.text
    return response.json()


def _assert_safe(value: dict[str, Any], forbidden: tuple[str, ...]) -> None:
    """Response/Trace 不能复制 raw recent turns、文档正文或完整 rows。"""

    serialized = json.dumps(value, ensure_ascii=False)
    for raw in forbidden:
        assert raw not in serialized


def worker_a(database_url: str) -> None:
    """重启前完成 canonical T1→T6；T6 前触发五轮 Compact。"""

    app = _application(database_url, OUTPUT / "process-a-trace.jsonl")
    turns: list[dict[str, Any]] = []
    with TestClient(app) as client:
        current = None
        for question in QUESTIONS[:6]:
            current = _turn(client, question, current)
            turns.append(current)
    assert current is not None
    assert turns[1]["rows"] == [
        {"period": "2026-07", "value": 120000},
        {"period": "2026-08", "value": 180000},
    ]
    assert sum(int(row["increment"]) for row in turns[2]["rows"]) == 60000
    t4_child = next(
        item["observation"]["diagnostics"]["b4_subgraph"]
        for item in turns[3]["action_attempts"]
        if item["action_id"] == "collect_document_evidence"
    )
    assert t4_child["termination"] == "answer_ready"
    assert turns[3]["answer_status"] == "complete" and turns[3]["citations"]
    assert sum(int(row["increment"]) for row in turns[4]["rows"]) == 60000
    assert turns[5]["compact_decision"]["outcome"] == "triggered_and_committed"
    assert turns[5]["task_context"]["compact_source_turn_range"] == [1, 5]
    assert turns[5]["task_context"]["recent_raw_turn_count"] == 2
    _assert_safe(turns[5], (QUESTIONS[3], QUESTIONS[4]))
    _json(OUTPUT / "handoff.json", {
        "task": current["task"],
        "compact_identity": current["task_context"]["compact_identity"],
        "process_a": {
            "versions": [item["task"]["task_version"] for item in turns],
            "t4_child": t4_child,
            "t6_context": current["task_context"],
        },
    })


def _mutate_context(database_url: str, task_id: str, *, mode: str) -> None:
    """只对 P2 synthetic row 注入 source-gap/corruption，验证 fail-closed。"""

    engine = create_engine(database_url, future=True)
    boundary = MySQLTaskBoundary(engine)
    key = boundary._task_key(task_id)  # 探针需要按 raw task 精确定位自己的隔离行。
    with engine.begin() as connection:
        if mode == "source_gap":
            payload_before = connection.scalar(select(AgentTaskCheckpoint.context_payload).where(
                AgentTaskCheckpoint.task_key == key,
            ))
            context = replace(TaskContextCodec().decode(payload_before), source_complete=False)
            payload = TaskContextCodec().encode(context)
            connection.execute(update(AgentTaskCheckpoint).where(
                AgentTaskCheckpoint.task_key == key,
            ).values(
                context_schema_version=context.context_version,
                context_identity=context.identity, context_payload=payload,
                context_source_watermark=context.source_watermark,
            ))
        elif mode == "corrupt_identity":
            connection.execute(update(AgentTaskCheckpoint).where(
                AgentTaskCheckpoint.task_key == key,
            ).values(context_identity="0" * 64))
        else:
            raise ValueError(mode)


def worker_b(database_url: str) -> None:
    """新进程 resume，并执行 ACL/version/competition/source integrity 负例。"""

    handoff = json.loads((OUTPUT / "handoff.json").read_text(encoding="utf-8"))
    previous = {"task": handoff["task"]}
    app = _application(database_url, OUTPUT / "process-b-trace.jsonl")
    with TestClient(app) as client:
        resumed = _turn(client, QUESTIONS[6], previous)
        assert resumed["task_context"]["compact_identity"] == handoff["compact_identity"]
        assert resumed["task_delta"]["category"] == "correct_previous_understanding"
        assert resumed["answer_status"] == "complete"
        assert sum(int(row["increment"]) for row in resumed["rows"]) == 60000

        role_drift = _turn(client, "继续。", resumed, role="admin")
        assert role_drift["task_action"] == "rejected"
        assert role_drift["reason_code"] == "task_unavailable"
        assert role_drift["task_runtime_invocation_count"] == 0

        stale = {"task": dict(resumed["task"], task_version=resumed["task"]["task_version"] - 1)}
        stale_result = _turn(client, "继续。", stale)
        assert stale_result["task_action"] == "rejected"
        assert stale_result["reason_code"] == "task_version_conflict"

        # 两个 API worker 竞争同一 version，只能有一次实际 runtime invocation。
        def compete(question: str) -> dict[str, Any]:
            return _turn(client, question, resumed)

        with ThreadPoolExecutor(max_workers=2) as pool:
            competition = list(pool.map(compete, ("解释渠道结果。", "再次解释渠道结果。")))
        assert sum(item["task_runtime_invocation_count"] for item in competition) == 1
        assert sorted(item["task_action"] for item in competition) == ["continue", "rejected"]

        # source gap 需要到 compact trigger 才应失败关闭。
        gap = None
        for ordinal in range(5):
            gap = _turn(client, f"查询 2026 年 7 月实际净退款金额，source gap {ordinal}。", gap)
        assert gap is not None
        _mutate_context(database_url, gap["task"]["task_id"], mode="source_gap")
        gap_result = _turn(client, "继续并触发 Compact。", gap)
        assert gap_result["task_action"] == "rejected"
        assert gap_result["reason_code"] == "task_compact_source_incomplete"
        assert gap_result["task_runtime_invocation_count"] == 0

        corrupt = _turn(client, "查询 2026 年 7 月实际净退款金额。")
        _mutate_context(database_url, corrupt["task"]["task_id"], mode="corrupt_identity")
        corrupt_result = _turn(client, "继续。", corrupt)
        assert corrupt_result["task_action"] == "rejected"
        assert corrupt_result["reason_code"] == "task_compact_identity_mismatch"
        assert corrupt_result["task_runtime_invocation_count"] == 0

    _assert_safe(resumed, (QUESTIONS[3], QUESTIONS[4]))
    _json(OUTPUT / "process-b.json", {
        "resumed": resumed,
        "role_drift": {"reason_code": role_drift["reason_code"], "invocations": 0},
        "stale_version": {"reason_code": stale_result["reason_code"], "invocations": 0},
        "competition": [{
            "action": item["task_action"], "reason_code": item["reason_code"],
            "invocations": item["task_runtime_invocation_count"],
        } for item in competition],
        "source_gap": {"reason_code": gap_result["reason_code"], "invocations": 0},
        "corruption": {"reason_code": corrupt_result["reason_code"], "invocations": 0},
    })


def _prepare_database(target_url: str) -> dict[str, Any]:
    """重建获准的隔离库 schema，并写入 deterministic Phase 4B seed。"""

    os.environ["DATABASE_URL"] = target_url
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    engine = create_engine(target_url, future=True)
    # P1 库只含基础设施表；P2 在同一获准隔离库重建完整 migration world。
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in inspect(engine).get_table_names():
            connection.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    command.upgrade(cfg, HEAD)
    import scripts.seed_data as seed_module

    seed_module.SEED_SUMMARY_PATH = OUTPUT / "seed-summary.md"
    with Session(engine) as session:
        summary = seed_module.seed_database(session, reset_existing=True, profile_alias="phase4b")
    return summary


def full() -> None:
    """父进程执行完整 Gate，始终精确清理 Agent synthetic rows。"""

    OUTPUT.mkdir(parents=True, exist_ok=True)
    # 每次获准重验都只统计本 attempt；历史 attempt 的结论已经固化在 notes，不能混入
    # 当前 Trace 数量或让旧 handoff 掩盖 worker 未写完。
    for name in ("process-a-trace.jsonl", "process-b-trace.jsonl", "handoff.json", "process-b.json"):
        path = OUTPUT / name
        if path.exists():
            path.unlink()
    source = make_url(get_settings().database_url)
    if source.get_backend_name() != "mysql":
        raise RuntimeError("M48-P2 必须使用真实 MySQL URL")
    target = source.set(database=TARGET_DATABASE)
    if target.database != TARGET_DATABASE:
        raise RuntimeError("M48-P2 拒绝非隔离数据库")
    admin = source.set(database=None)
    with create_engine(admin, future=True).begin() as connection:
        connection.execute(text(f"CREATE DATABASE IF NOT EXISTS `{TARGET_DATABASE}` CHARACTER SET utf8mb4"))
    target_url = target.render_as_string(hide_password=False)
    seed = _prepare_database(target_url)
    env = dict(os.environ, DATABASE_URL=target_url)
    engine = create_engine(target_url, future=True)
    try:
        subprocess.run([sys.executable, __file__, "worker-a"], check=True, env=env)
        subprocess.run([sys.executable, __file__, "worker-b"], check=True, env=env)
        handoff = json.loads((OUTPUT / "handoff.json").read_text(encoding="utf-8"))
        process_b = json.loads((OUTPUT / "process-b.json").read_text(encoding="utf-8"))
        trace_a = [json.loads(line) for line in (OUTPUT / "process-a-trace.jsonl").read_text(encoding="utf-8").splitlines()]
        trace_b = [json.loads(line) for line in (OUTPUT / "process-b-trace.jsonl").read_text(encoding="utf-8").splitlines()]
        _assert_safe(trace_a[-1], (QUESTIONS[3], QUESTIONS[4]))
        assert trace_a[-1]["task_context"]["compact_identity"] == handoff["compact_identity"]
        assert process_b["resumed"]["task_context"]["compact_identity"] == handoff["compact_identity"]
        with engine.connect() as connection:
            rows_before = {
                "checkpoints": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)) or 0),
                "events": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)) or 0),
            }
        result = {
            "probe_id": "M48-P2", "classification": "exploratory",
            "baseline_eligible": False, "decision": "continue", "database": TARGET_DATABASE,
            "migration_head": HEAD, "seed_identity": seed["seed_profile"]["content_identity"],
            "processes": 2, "canonical_versions": handoff["process_a"]["versions"],
            "compact_identity": handoff["compact_identity"],
            "compact_source_turn_range": handoff["process_a"]["t6_context"]["compact_source_turn_range"],
            "restart_continuation": "passed", "sql_guard_oracle": "passed",
            "oracle": {"july": 120000, "august": 180000, "delta": 60000, "growth": "50%"},
            "business_subgraph": handoff["process_a"]["t4_child"],
            "negative_paths": {
                key: process_b[key] for key in ("role_drift", "stale_version", "competition", "source_gap", "corruption")
            },
            "response_trace_redaction": "passed", "provider_calls": 0, "tokens": 0,
            "rows_before_cleanup": rows_before, "business_seed_retained": True,
            "trace_records": len(trace_a) + len(trace_b),
        }
    finally:
        with engine.begin() as connection:
            connection.execute(delete(AgentTaskEvent))
            connection.execute(delete(AgentTaskCheckpoint))
    with engine.connect() as connection:
        result["rows_after_cleanup"] = {
            "checkpoints": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)) or 0),
            "events": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)) or 0),
        }
    assert result["rows_after_cleanup"] == {"checkpoints": 0, "events": 0}
    _json(OUTPUT / "result.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    url = os.environ.get("DATABASE_URL", "")
    if mode == "worker-a":
        worker_a(url)
    elif mode == "worker-b":
        worker_b(url)
    elif mode == "full":
        full()
    else:
        raise SystemExit(f"unknown mode: {mode}")
