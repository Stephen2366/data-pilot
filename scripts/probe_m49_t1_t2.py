"""M49-P1：真实 Qwen + Text2SQL + MySQL 的受影响 T1→T2 最小探针。

只连接既有 ``datapilot_m48_test``，不建库、不迁移、不 reset/reseed。运行前要求
0005、7/8 月 oracle 和 task 表空；首次系统性失败立即停止，finally 精确清空本次
synthetic task rows。它是 exploratory/baseline-ineligible 开发证据，不是 Formal Eval。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent

TARGET_DATABASE = "datapilot_m48_test"
HEAD = "20260827_0005"
OUTPUT = Path(os.environ.get("M49_P1_OUTPUT", ".agent_work/temp/m49/probe-p1"))
MAX_PROVIDER_CALLS = 4
MAX_OBSERVED_TOKENS = 20_000
QUESTIONS = (
    ("T1", "查询 2026 年 7 月实际净退款金额。"),
    ("T2", "比较 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。"),
)


def _write_json(path: Path, payload: Any) -> None:
    """把每次 attempt 写入独立 UTF-8 artifact，禁止覆盖旧失败证据。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _target_url() -> str:
    """从现有 MySQL URL 只替换库名，并拒绝非隔离数据库目标。"""

    source = make_url(get_settings().database_url)
    if source.get_backend_name() != "mysql":
        raise RuntimeError("m49_p1_requires_mysql")
    target = source.set(database=TARGET_DATABASE)
    if target.database != TARGET_DATABASE:
        raise RuntimeError("m49_p1_database_mismatch")
    return target.render_as_string(hide_password=False)


def _settings(database_url: str) -> Settings:
    """固定 Probe 的模型、retry、task backend 与禁用的旁路配置。"""

    base = get_settings()
    return Settings(
        _env_file=None,
        APP_ENV="local",
        DATABASE_URL=database_url,
        TASK_BOUNDARY_BACKEND="mysql",
        PHASE4B_RAG_STRATEGY="pipeline",
        LLM_PROVIDER="qwen",
        QWEN_MODEL="qwen3.7-plus",
        DASHSCOPE_API_KEY=base.dashscope_api_key,
        DASHSCOPE_BASE_URL=base.dashscope_base_url,
        LLM_TIMEOUT_SECONDS=120,
        LLM_MAX_RETRIES=0,
        LLM_RETRY_BACKOFF_SECONDS=1,
        LANGFUSE_ENABLED=False,
    )


def _application(database_url: str, trace_path: Path):
    """组装与产品相同的 Qwen/Text2SQL 路径，只替换隔离数据库和 Trace 路径。"""

    engine = create_engine(database_url, future=True)
    maker = sessionmaker(engine, expire_on_commit=False)
    application = create_app(_settings(database_url))
    application.state.trace_path = trace_path

    def override_db() -> Generator[Session, None, None]:
        """让 TestClient 与只读门禁共用同一个隔离数据库 engine。"""

        with maker() as session:
            yield session

    application.dependency_overrides[get_db] = override_db
    return application


def _counts(engine) -> dict[str, int]:
    """只读统计 synthetic task 行，供运行前门禁与 finally 清理核对。"""

    with engine.connect() as connection:
        return {
            "checkpoints": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)) or 0),
            "events": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)) or 0),
        }


def _database_facts(engine) -> dict[str, str]:
    """核对 migration 与两期 oracle，防止数据世界漂移后仍继续消费预算。"""

    with engine.connect() as connection:
        return {
            "migration": str(connection.scalar(text("select version_num from alembic_version"))),
            "july": str(connection.scalar(text(
                "select coalesce(sum(refund_amount),0) from refunds "
                "where refund_status='completed' and processed_at >= '2026-07-01' "
                "and processed_at < '2026-08-01'"
            ))),
            "august": str(connection.scalar(text(
                "select coalesce(sum(refund_amount),0) from refunds "
                "where refund_status='completed' and processed_at >= '2026-08-01' "
                "and processed_at < '2026-09-01'"
            ))),
        }


def _summary(turn_id: str, body: dict[str, Any], http_status: int) -> dict[str, Any]:
    """从完整 Response 提取可归档安全摘要，同时保留判门所需 typed rows。"""

    consumed = ((body.get("agent_budget") or {}).get("consumed") or {})
    termination = body.get("agent_termination") or {}
    return {
        "turn_id": turn_id,
        "http_status": http_status,
        "trace_id": body.get("trace_id"),
        "task_version": ((body.get("task") or {}).get("task_version")),
        "delta_category": ((body.get("task_delta") or {}).get("category")),
        "route": body.get("route"),
        "execution_status": body.get("execution_status"),
        "answer_status": body.get("answer_status"),
        "safety_status": body.get("safety_status"),
        "reason_code": body.get("reason_code"),
        "active_requirements": termination.get("active_requirement_identities") or [],
        "unresolved_requirements": termination.get("unresolved_requirement_identities") or [],
        "action_ids": [item.get("action_id") for item in body.get("action_attempts") or []],
        "provider_calls": int(consumed.get("model_calls", 0) or 0),
        "observed_tokens": int(consumed.get("total_tokens", 0) or 0),
        "token_usage_observed": bool(consumed.get("token_usage_observed")),
        "rows": body.get("rows") or [],
        "runtime_invocations": body.get("task_runtime_invocation_count"),
    }


def _request(client: TestClient, turn_id: str, question: str, previous: dict[str, Any] | None):
    """发送 start/continue，并把上一轮服务端 task version 原样带入下一轮。"""

    task = {"action": "start"} if previous is None else {
        "action": "continue",
        "task_id": previous["task"]["task_id"],
        "expected_version": previous["task"]["task_version"],
    }
    response = client.post(
        "/api/query",
        json={"question": question, "user_role": "ops", "task": task},
    )
    body = response.json()
    return body, _summary(turn_id, body, response.status_code)


def _comparison_rows_match(rows: list[dict[str, Any]]) -> bool:
    """按 typed 语义核对两期结果，不把某个 SQL projection 列名当成业务合同。

    真实 Text2SQL/repair 使用 ``month + net_refund_amount``；M48 frozen oracle 使用
    ``period + value``。两者都能表达相同事实，Probe 应核对月份、指标、差额和变化率，
    不能反过来要求真实链模仿 fake oracle 的列形状。
    """

    if len(rows) != 2:
        return False
    normalized: dict[str, tuple[float, dict[str, Any]]] = {}
    for row in rows:
        raw_period = row.get("period", row.get("month"))
        period = str(raw_period)[:7] if raw_period is not None else ""
        raw_value = row.get("value", row.get("net_refund_amount"))
        try:
            normalized[period] = (float(raw_value), row)
        except (TypeError, ValueError):
            return False
    if {key: value[0] for key, value in normalized.items()} != {
        "2026-07": 120000.0,
        "2026-08": 180000.0,
    }:
        return False
    comparison = normalized["2026-08"][1]
    raw_delta = comparison.get("delta", comparison.get("diff"))
    raw_rate = comparison.get("rate", comparison.get("change_rate"))
    try:
        return float(raw_delta) == 60000.0 and float(raw_rate) == 0.5
    except (TypeError, ValueError):
        return False


def _semantic_failure(turns: list[dict[str, Any]], after: dict[str, int]) -> dict[str, Any] | None:
    """从安全 turn summary 统一计算 P1 Gate，供在线与离线复核共用。"""

    if len(turns) != 2:
        return {"layer": "sequence_incomplete", "turn_count": len(turns)}
    for turn in turns:
        if turn["http_status"] != 200 or turn["safety_status"] != "passed" or turn["answer_status"] != "complete":
            return {
                "turn_id": turn["turn_id"],
                "layer": "agent_result",
                "reason_code": turn["reason_code"],
            }
    if turns[1]["delta_category"] != "modify_constraint":
        return {"turn_id": "T2", "layer": "task_delta", "actual": turns[1]["delta_category"]}
    if turns[1]["active_requirements"] != ["sql:net_refund_amount:2026-07,2026-08"]:
        return {"turn_id": "T2", "layer": "requirement_merge", "actual": turns[1]["active_requirements"]}
    if not _comparison_rows_match(turns[1]["rows"]):
        return {"turn_id": "T2", "layer": "sql_oracle", "actual": turns[1]["rows"]}
    if after != {"checkpoints": 0, "events": 0}:
        return {"layer": "cleanup", "actual": after}
    return None


def verify_existing() -> None:
    """离线复核已完成 attempt；不调用 provider，也不连接或写入数据库。"""

    source_path = OUTPUT / "result-safe.json"
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    failure = _semantic_failure(source["turns"], source["rows_after_cleanup"])
    verification = {
        "artifact_family": "m49-live-dev-probe-p1-offline-verification-v1",
        "source_result_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_probe_id": source["probe_id"],
        "source_usage": source["usage"],
        "provider_calls_added": 0,
        "database_writes_added": 0,
        "decision": "continue" if failure is None else "revise",
        "first_failure": failure,
        "semantic_assertions": {
            "t1_complete": source["turns"][0]["answer_status"] == "complete",
            "t2_complete": source["turns"][1]["answer_status"] == "complete",
            "single_comparison_requirement": source["turns"][1]["active_requirements"]
            == ["sql:net_refund_amount:2026-07,2026-08"],
            "oracle_120000_180000_60000_50pct": _comparison_rows_match(source["turns"][1]["rows"]),
            "cleanup_zero": source["rows_after_cleanup"] == {"checkpoints": 0, "events": 0},
        },
    }
    _write_json(OUTPUT / "verification-safe.json", verification)
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    if failure is not None:
        raise SystemExit(21)


def main() -> None:
    """执行两轮、判定首错、写安全汇总并始终清理 task/event。"""

    OUTPUT.mkdir(parents=True, exist_ok=False)
    database_url = _target_url()
    engine = create_engine(database_url, future=True)
    before = _counts(engine)
    facts = _database_facts(engine)
    if before != {"checkpoints": 0, "events": 0}:
        raise RuntimeError(f"m49_p1_nonempty_task_tables:{before}")
    if facts != {"migration": HEAD, "july": "120000.00", "august": "180000.00"}:
        raise RuntimeError(f"m49_p1_database_fact_mismatch:{facts}")

    turns: list[dict[str, Any]] = []
    calls = tokens = 0
    current: dict[str, Any] | None = None
    first_failure: dict[str, Any] | None = None
    rows_before_cleanup = before
    trace_path = OUTPUT / "trace.jsonl"
    try:
        application = _application(database_url, trace_path)
        with TestClient(application) as client:
            for turn_id, question in QUESTIONS:
                body, summary = _request(client, turn_id, question, current)
                _write_json(OUTPUT / f"{turn_id.lower()}-response.json", body)
                turns.append(summary)
                calls += summary["provider_calls"]
                tokens += summary["observed_tokens"]
                if calls > MAX_PROVIDER_CALLS or tokens > MAX_OBSERVED_TOKENS:
                    first_failure = {
                        "turn_id": turn_id,
                        "layer": "authorized_budget_stop",
                        "calls": calls,
                        "tokens": tokens,
                    }
                    break
                if summary["http_status"] != 200 or body.get("task") is None:
                    first_failure = {
                        "turn_id": turn_id,
                        "layer": "http_or_task_boundary",
                        "reason_code": summary["reason_code"],
                    }
                    break
                current = body
                if summary["safety_status"] != "passed" or summary["answer_status"] != "complete":
                    first_failure = {
                        "turn_id": turn_id,
                        "layer": "agent_result",
                        "reason_code": summary["reason_code"],
                    }
                    break
        rows_before_cleanup = _counts(engine)
    finally:
        with engine.begin() as connection:
            connection.execute(delete(AgentTaskEvent))
            connection.execute(delete(AgentTaskCheckpoint))

    after = _counts(engine)
    if first_failure is None:
        first_failure = _semantic_failure(turns, after)

    artifact = {
        "artifact_family": "m49-live-dev-probe-p1-v1",
        "probe_id": "M49-P1",
        "classification": ["exploratory", "baseline-ineligible", "development-probe"],
        "executed_at": datetime.now(UTC).isoformat(),
        "database": TARGET_DATABASE,
        "database_facts": facts,
        "limits": {
            "provider_calls": MAX_PROVIDER_CALLS,
            "observed_tokens": MAX_OBSERVED_TOKENS,
            "retry": 0,
        },
        "turns": turns,
        "usage": {"provider_calls": calls, "observed_tokens": tokens},
        "first_failure": first_failure,
        "decision": "continue" if first_failure is None else "revise",
        "rows_before_run": before,
        "rows_before_cleanup": rows_before_cleanup,
        "rows_after_cleanup": after,
        "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path.exists() else None,
    }
    _write_json(OUTPUT / "result-safe.json", artifact)
    print(json.dumps({
        "decision": artifact["decision"],
        "usage": artifact["usage"],
        "first_failure": first_failure,
        "turns": turns,
        "rows_after_cleanup": after,
        "artifact": str(OUTPUT / "result-safe.json"),
    }, ensure_ascii=False, indent=2))
    if first_failure is not None:
        raise SystemExit(20)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify-existing":
        verify_existing()
    else:
        main()
