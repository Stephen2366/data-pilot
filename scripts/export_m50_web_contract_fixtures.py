"""导出 M50 前后端共用合同 fixture 与 JSON Schema。

★ Pydantic 是唯一业务合同 authority。这个脚本先用真实 Model 构造代表性公开响应，再写入
Web 测试目录；TypeScript/Zod 只负责验证这些网络边界样本。fixture identity 绑定所有文件
内容，后端合同变化却没有重签时，Python 测试会直接失败。

本脚本只写仓库内可复用的合同产物，不连接数据库、不调用 Tool/LLM/provider。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.schemas.agent import (
    AgentResponse,
    ClarificationFieldView,
    ClarificationView,
    QueryRequest,
    TaskControlResponse,
    TaskView,
    ThreadControlResponse,
    ThreadView,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "web" / "test" / "fixtures"
CONTRACT_DIR = ROOT / "web" / "contracts"
FORMAT = "m50-web-contract-fixtures-v1"


def _json_bytes(value: Any) -> bytes:
    """使用稳定 JSON 编码，避免格式化差异制造 identity 漂移。"""

    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _task(version: int = 1) -> TaskView:
    """构造不含 owner/raw rows 的 task 安全投影。"""

    return TaskView(
        task_id="task_m50_fixture_001",
        task_version=version,
        status="active",
        expires_at="2026-08-28T12:15:00+00:00",
        state={"goal": "分析实际净退款金额", "route": "sql", "requirement_count": 1},
        context={"format": "phase4b-task-context-v2", "committed_turn_count": version},
    )


def response_fixtures() -> dict[str, dict[str, Any]]:
    """覆盖 M50 presenter 必须区分的主要产品状态与两套 runtime family。"""

    common = {"safety_status": "passed"}
    sql_complete = AgentResponse(
        **common,
        trace_id="trace-m50-fixture",
        route="sql",
        answer="2026 年 7 月实际净退款金额为 120,000 元。",
        sql="SELECT SUM(refund_amount) AS net_refund_amount FROM refunds",
        columns=["month", "net_refund_amount"],
        rows=[{"month": "2026-07", "net_refund_amount": 120000.0}],
        tables_used=["refunds"],
        chart_spec={
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "mark": "bar",
            "data": {"values": [{"month": "2026-07", "amount": 120000.0}]},
            "encoding": {"x": {"field": "month"}, "y": {"field": "amount", "type": "quantitative"}},
        },
        execution_status="completed",
        answer_status="complete",
        runtime_family="agent_task",
        task_action="start",
        task_runtime_invocation_count=1,
        task=_task(),
        task_delta={"category": "start", "changed_fields": ["goal", "requirements"]},
        task_transition={"from": "new", "to": "active", "committed_version": 1},
        action_attempts=[{"action": "query_sql", "status": "completed", "evidence_delta": 1}],
        agent_budget={"sql": {"used": 1, "limit": 2}},
        agent_termination={"reason": "requirements_satisfied", "action": "answer"},
        agent_loop_runtime={"format": "phase4b-agent-loop-v1"},
        task_context={"format": "phase4b-task-context-v2", "committed_turn_count": 1},
    )
    hybrid_partial = AgentResponse(
        **common,
        trace_id="trace-m50-hybrid",
        route="hybrid",
        answer="SQL 指标已完成；政策证据只覆盖部分要求。",
        columns=["month", "net_refund_amount"],
        rows=[
            {"month": "2026-07", "net_refund_amount": 120000.0},
            {"month": "2026-08", "net_refund_amount": 180000.0},
        ],
        execution_status="completed",
        answer_status="partial",
        reason_code="required_coverage_incomplete",
        runtime_family="agent_task",
        task_action="continue",
        task_runtime_invocation_count=1,
        task=_task(3),
        citations=[{"title": "基础退款政策", "anchor": "section:refund-window", "evidence_id": "ev-safe-1"}],
        hybrid_branches=[
            {"branch": "sql", "answer_status": "complete", "safety_status": "passed", "reason_code": "completed"},
            {"branch": "rag", "answer_status": "partial", "safety_status": "passed", "reason_code": "required_coverage_incomplete"},
        ],
        knowledge_runtimes=[{"scope": "business_release", "strategy": "pipeline", "rollout": "default"}],
        action_attempts=[{"action": "query_sql", "status": "completed"}, {"action": "retrieve_knowledge", "status": "completed"}],
        agent_budget={"sql": {"used": 1, "limit": 2}, "knowledge": {"used": 1, "limit": 1}},
        agent_termination={"reason": "budget_exhausted", "action": "partial_answer"},
    )
    blocked = AgentResponse(
        route="none",
        answer="",
        safety_status="blocked",
        blocked_reason="请求涉及受保护字段。",
        trace_id="trace-m50-blocked",
        execution_status="not_started",
        answer_status="no_answer",
        reason_code="sensitive_field_blocked",
        runtime_family="agent_task",
        task_action="rejected",
        task_runtime_invocation_count=0,
    )
    unavailable = AgentResponse(
        **common,
        trace_id="trace-m50-unavailable",
        route="rag",
        answer="",
        execution_status="external_unavailable",
        answer_status="no_answer",
        reason_code="enterprise_rag_runtime_unavailable",
    )
    clarification = AgentResponse(
        **common,
        trace_id="trace-m50-legacy",
        route="none",
        answer="请补充要分析的月份。",
        execution_status="not_started",
        answer_status="clarification_required",
        reason_code="clarification_required",
        graph_invocation_count=0,
        thread=ThreadView(
            thread_id="thread_m50_fixture_001",
            checkpoint_version=1,
            state_version="phase4-turn-state-v1",
            status="pending",
            expires_at="2026-08-28T12:15:00+00:00",
            clarification=ClarificationView(
                identity="clarification-m50-v1",
                prompt="请选择月份。",
                fields=[ClarificationFieldView(key="month", label="月份", value_type="time_range", max_length=32)],
            ),
            follow_up_budget_remaining=0,
        ),
    )
    return {
        "sql-complete.json": sql_complete.model_dump(mode="json"),
        "hybrid-partial.json": hybrid_partial.model_dump(mode="json"),
        "blocked.json": blocked.model_dump(mode="json"),
        "external-unavailable.json": unavailable.model_dump(mode="json"),
        "legacy-clarification.json": clarification.model_dump(mode="json"),
    }


def export() -> dict[str, Any]:
    """写入 fixtures/schema/manifest，并返回可供命令行展示的安全摘要。"""

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {}
    for name, payload in response_fixtures().items():
        files[f"test/fixtures/{name}"] = _json_bytes(payload)
    schema_payloads = {
        "query-request.schema.json": QueryRequest.model_json_schema(),
        "agent-response.schema.json": AgentResponse.model_json_schema(),
        "task-control-response.schema.json": TaskControlResponse.model_json_schema(),
        "thread-control-response.schema.json": ThreadControlResponse.model_json_schema(),
    }
    for name, payload in schema_payloads.items():
        files[f"contracts/{name}"] = _json_bytes(payload)

    hashes: dict[str, str] = {}
    for relative, content in sorted(files.items()):
        target = ROOT / "web" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        hashes[relative] = hashlib.sha256(content).hexdigest()
    identity = hashlib.sha256(_json_bytes({"format": FORMAT, "files": hashes})).hexdigest()
    manifest = {"format": FORMAT, "identity": identity, "files": hashes, "authority": "app.schemas.agent"}
    (CONTRACT_DIR / "manifest.json").write_bytes(_json_bytes(manifest))
    return {"format": FORMAT, "identity": identity, "fixture_count": len(response_fixtures()), "provider_calls": 0}


if __name__ == "__main__":
    print(json.dumps(export(), ensure_ascii=False, indent=2))
