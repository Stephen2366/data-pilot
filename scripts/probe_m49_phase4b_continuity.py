"""M49-P2：真实 Qwen/MySQL/Subgraph/Compact/restart 的连续 Phase 4B 探针。

只消费既有 ``datapilot_m48_test`` 的 0005 + Phase 4B deterministic business seed；
不建库、不迁移、不 reset/reseed。worker A/B 是两个独立进程，唯一共享恢复事实为
MySQL task boundary。首次系统性失败停止，finally 清空 synthetic task/event rows。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
OUTPUT = Path(os.environ.get("M49_P2_OUTPUT", ".agent_work/temp/m49/probe-p2"))
MAX_PROVIDER_CALLS = 14
MAX_OBSERVED_TOKENS = 60_000
QUESTIONS = (
    ("T1", "查询 2026 年 7 月实际净退款金额。"),
    ("T2", "比较 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。"),
    ("T3", "2026 年 7 月和 8 月质量问题对净退款增长贡献了多少？哪些商品最突出？"),
    ("T4", "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。"),
    ("T5", "更正为按渠道比较 2026 年 7 月和 8 月，并重新核验质量问题全额退款的前提和材料。"),
    ("T6", "解释这个结果。"),
)


def _write_json(path: Path, payload: Any) -> None:
    """写入本 attempt 独立 artifact；旧 attempt 目录永不覆盖。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _target_url() -> str:
    """只允许连接预注册的隔离 MySQL 库，避免误写默认开发库。"""

    source = make_url(get_settings().database_url)
    if source.get_backend_name() != "mysql":
        raise RuntimeError("m49_p2_requires_mysql")
    target = source.set(database=TARGET_DATABASE)
    if target.database != TARGET_DATABASE:
        raise RuntimeError("m49_p2_database_mismatch")
    return target.render_as_string(hide_password=False)


def _settings(database_url: str, *, app_env: str) -> Settings:
    """冻结真实链的 provider、retry、Subgraph 策略和 task backend。"""

    base = get_settings()
    return Settings(
        _env_file=None,
        APP_ENV=app_env,
        DATABASE_URL=database_url,
        TASK_BOUNDARY_BACKEND="mysql",
        PHASE4B_RAG_STRATEGY="subgraph",
        LLM_PROVIDER="qwen",
        QWEN_MODEL="qwen3.7-plus",
        DASHSCOPE_API_KEY=base.dashscope_api_key,
        DASHSCOPE_BASE_URL=base.dashscope_base_url,
        LLM_TIMEOUT_SECONDS=120,
        LLM_MAX_RETRIES=0,
        LLM_RETRY_BACKOFF_SECONDS=1,
        LANGFUSE_ENABLED=False,
    )


def _application(database_url: str, trace_path: Path, *, app_env: str = "local"):
    """每个 worker 独立组装产品 runtime；不注入 SQL fake 或 frozen oracle。"""

    engine = create_engine(database_url, future=True)
    maker = sessionmaker(engine, expire_on_commit=False)
    application = create_app(_settings(database_url, app_env=app_env))
    application.state.trace_path = trace_path

    def override_db() -> Generator[Session, None, None]:
        """把 API session 固定到预注册隔离库，不读取默认开发库连接。"""

        with maker() as session:
            yield session

    application.dependency_overrides[get_db] = override_db
    return application


def _counts(engine) -> dict[str, int]:
    """统计 synthetic checkpoint/event 行，验证运行前与 finally 后均为零。"""

    with engine.connect() as connection:
        return {
            "checkpoints": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)) or 0),
            "events": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)) or 0),
        }


def _facts(engine) -> dict[str, str]:
    """核对 migration 与 7/8 月 oracle，数据身份不符时在 provider 前停止。"""

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
    """把 Response 收敛为无 task id/正文的 Gate 摘要。"""

    consumed = ((body.get("agent_budget") or {}).get("consumed") or {})
    termination = body.get("agent_termination") or {}
    context = body.get("task_context") or {}
    compact = body.get("compact_decision") or {}
    attempts = body.get("action_attempts") or []
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
        "action_ids": [item.get("action_id") for item in attempts],
        "action_statuses": [item.get("status") for item in attempts],
        "provider_calls": int(consumed.get("model_calls", 0) or 0),
        "observed_tokens": int(consumed.get("total_tokens", 0) or 0),
        "token_usage_observed": bool(consumed.get("token_usage_observed")),
        "citations_count": len(body.get("citations") or []),
        "knowledge_runtimes": body.get("knowledge_runtimes") or [],
        "compact_outcome": compact.get("outcome"),
        "compact_identity": context.get("compact_identity"),
        "compact_source_turn_range": context.get("compact_source_turn_range"),
        "runtime_invocations": body.get("task_runtime_invocation_count"),
        "rows_count": len(body.get("rows") or []),
    }


def _request(client: TestClient, turn_id: str, question: str, previous: dict[str, Any] | None):
    """按服务端返回 version 串联 start/continue，保持唯一 task lineage。"""

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


def _turn_failure(summary: dict[str, Any]) -> dict[str, Any] | None:
    """返回首个系统性失败；未失败返回 None，让 runner 继续下一 turn。"""

    if summary["http_status"] != 200 or summary["task_version"] is None:
        return {"turn_id": summary["turn_id"], "layer": "http_or_task_boundary", "reason_code": summary["reason_code"]}
    if summary["safety_status"] != "passed" or summary["answer_status"] != "complete":
        return {
            "turn_id": summary["turn_id"],
            "layer": "agent_result",
            "reason_code": summary["reason_code"],
            "answer_status": summary["answer_status"],
        }
    return None


def worker_a(database_url: str) -> None:
    """在进程 A 完成 T1→T5；任何失败立即写 handoff 后停止。"""

    app = _application(database_url, OUTPUT / "worker-a-trace.jsonl")
    current: dict[str, Any] | None = None
    turns: list[dict[str, Any]] = []
    calls = tokens = 0
    failure: dict[str, Any] | None = None
    with TestClient(app) as client:
        for turn_id, question in QUESTIONS[:5]:
            body, summary = _request(client, turn_id, question, current)
            _write_json(OUTPUT / f"{turn_id.lower()}-response.json", body)
            turns.append(summary)
            calls += summary["provider_calls"]
            tokens += summary["observed_tokens"]
            failure = _turn_failure(summary)
            if calls > MAX_PROVIDER_CALLS or tokens > MAX_OBSERVED_TOKENS:
                failure = {"turn_id": turn_id, "layer": "authorized_budget_stop", "calls": calls, "tokens": tokens}
            if body.get("task") is not None:
                current = body
            if failure is not None:
                break
    # T4 必须真实走 Document Evidence/Subgraph，不能仅因 answer complete 就放行。
    if failure is None:
        t4 = turns[3]
        if "collect_document_evidence" not in t4["action_ids"] or t4["citations_count"] == 0:
            failure = {"turn_id": "T4", "layer": "business_subgraph_not_observed"}
    _write_json(OUTPUT / "handoff-private.json", {
        "turns": turns,
        "usage": {"provider_calls": calls, "observed_tokens": tokens},
        "first_failure": failure,
        "task": current.get("task") if current else None,
    })
    if failure is not None:
        raise SystemExit(20)


def worker_b(database_url: str) -> None:
    """在新进程从 MySQL task boundary 恢复，并执行触发 Compact 的 T6。"""

    handoff = json.loads((OUTPUT / "handoff-private.json").read_text(encoding="utf-8"))
    calls = int(handoff["usage"]["provider_calls"])
    tokens = int(handoff["usage"]["observed_tokens"])
    if calls >= MAX_PROVIDER_CALLS or tokens >= MAX_OBSERVED_TOKENS:
        handoff["first_failure"] = {"turn_id": "T6", "layer": "authorized_budget_pre_stop", "calls": calls, "tokens": tokens}
        _write_json(OUTPUT / "handoff-private.json", handoff)
        raise SystemExit(21)
    previous = {"task": handoff["task"]}
    app = _application(database_url, OUTPUT / "worker-b-trace.jsonl")
    with TestClient(app) as client:
        body, summary = _request(client, QUESTIONS[5][0], QUESTIONS[5][1], previous)
    _write_json(OUTPUT / "t6-response.json", body)
    handoff["turns"].append(summary)
    handoff["usage"]["provider_calls"] = calls + summary["provider_calls"]
    handoff["usage"]["observed_tokens"] = tokens + summary["observed_tokens"]
    failure = _turn_failure(summary)
    if handoff["usage"]["provider_calls"] > MAX_PROVIDER_CALLS or handoff["usage"]["observed_tokens"] > MAX_OBSERVED_TOKENS:
        failure = {
            "turn_id": "T6", "layer": "authorized_budget_stop",
            "calls": handoff["usage"]["provider_calls"], "tokens": handoff["usage"]["observed_tokens"],
        }
    if failure is None and (
        summary["compact_outcome"] != "triggered_and_committed"
        or summary["compact_source_turn_range"] != [1, 5]
        or not summary["compact_identity"]
    ):
        failure = {"turn_id": "T6", "layer": "compact_or_restart", "summary": summary}
    handoff["first_failure"] = failure
    handoff["task"] = body.get("task")
    _write_json(OUTPUT / "handoff-private.json", handoff)
    if failure is not None:
        raise SystemExit(22)


def _safety(database_url: str) -> dict[str, Any]:
    """production-like 无 resolver 必须在 Tool/provider 前统一失败关闭。"""

    app = _application(database_url, OUTPUT / "safety-trace.jsonl", app_env="production")
    with TestClient(app) as client:
        response = client.post(
            "/api/query",
            json={"question": QUESTIONS[0][1], "user_role": "ops", "task": {"action": "start"}},
        )
    body = response.json()
    _write_json(OUTPUT / "safety-response.json", body)
    summary = _summary("S1", body, response.status_code)
    return {
        "http_status": summary["http_status"],
        "public_reason_code": summary["reason_code"],
        "safety_status": summary["safety_status"],
        "runtime_invocations": summary["runtime_invocations"],
        "provider_calls": summary["provider_calls"],
        "observed_tokens": summary["observed_tokens"],
        "task_created": body.get("task") is not None,
    }


def main() -> None:
    """父进程执行两个 worker、安全路径、safe artifact 与 finally cleanup。"""

    OUTPUT.mkdir(parents=True, exist_ok=False)
    database_url = _target_url()
    engine = create_engine(database_url, future=True)
    before = _counts(engine)
    facts = _facts(engine)
    if before != {"checkpoints": 0, "events": 0}:
        raise RuntimeError(f"m49_p2_nonempty_task_tables:{before}")
    if facts != {"migration": HEAD, "july": "120000.00", "august": "180000.00"}:
        raise RuntimeError(f"m49_p2_database_fact_mismatch:{facts}")

    worker_exit_codes: list[int] = []
    safety: dict[str, Any] | None = None
    handoff: dict[str, Any] = {"turns": [], "usage": {"provider_calls": 0, "observed_tokens": 0}, "first_failure": None}
    rows_before_cleanup = before
    try:
        env = dict(os.environ, DATABASE_URL=database_url, M49_P2_OUTPUT=str(OUTPUT))
        first = subprocess.run([sys.executable, __file__, "worker-a"], env=env, check=False)
        worker_exit_codes.append(first.returncode)
        handoff = json.loads((OUTPUT / "handoff-private.json").read_text(encoding="utf-8"))
        if first.returncode == 0:
            second = subprocess.run([sys.executable, __file__, "worker-b"], env=env, check=False)
            worker_exit_codes.append(second.returncode)
            handoff = json.loads((OUTPUT / "handoff-private.json").read_text(encoding="utf-8"))
        # 首错停止：主链完整通过后才执行独立的零 provider 安全路径。
        if handoff.get("first_failure") is None and worker_exit_codes == [0, 0]:
            safety = _safety(database_url)
        rows_before_cleanup = _counts(engine)
    finally:
        with engine.begin() as connection:
            connection.execute(delete(AgentTaskEvent))
            connection.execute(delete(AgentTaskCheckpoint))

    after = _counts(engine)
    failure = handoff.get("first_failure")
    if failure is None and safety is not None:
        safety_ok = (
            safety["public_reason_code"] == "task_unavailable"
            and safety["safety_status"] == "blocked"
            and safety["runtime_invocations"] == 0
            and safety["provider_calls"] == 0
            and not safety["task_created"]
        )
        if not safety_ok:
            failure = {"layer": "safety_path", "actual": safety}
    if failure is None and after != {"checkpoints": 0, "events": 0}:
        failure = {"layer": "cleanup", "actual": after}

    trace_hashes = {}
    for name in ("worker-a-trace.jsonl", "worker-b-trace.jsonl", "safety-trace.jsonl"):
        path = OUTPUT / name
        trace_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    artifact = {
        "artifact_family": "m49-live-dev-probe-p2-v1",
        "probe_id": "M49-P2",
        "classification": ["exploratory", "baseline-ineligible", "development-probe"],
        "executed_at": datetime.now(UTC).isoformat(),
        "database": TARGET_DATABASE,
        "database_facts": facts,
        "limits": {"provider_calls": MAX_PROVIDER_CALLS, "observed_tokens": MAX_OBSERVED_TOKENS, "retry": 0},
        "worker_exit_codes": worker_exit_codes,
        "turns": handoff["turns"],
        "usage": handoff["usage"],
        "safety_path": safety,
        "first_failure": failure,
        "decision": "continue" if failure is None else "revise",
        "rows_before_run": before,
        "rows_before_cleanup": rows_before_cleanup,
        "rows_after_cleanup": after,
        "trace_sha256": trace_hashes,
    }
    _write_json(OUTPUT / "result-safe.json", artifact)
    print(json.dumps({
        "decision": artifact["decision"], "usage": artifact["usage"],
        "first_failure": failure, "turns": artifact["turns"],
        "safety_path": safety, "rows_after_cleanup": after,
        "artifact": str(OUTPUT / "result-safe.json"),
    }, ensure_ascii=False, indent=2))
    if failure is not None:
        raise SystemExit(20)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    url = os.environ.get("DATABASE_URL") or _target_url()
    if mode == "worker-a":
        worker_a(url)
    elif mode == "worker-b":
        worker_b(url)
    elif mode == "full":
        main()
    else:
        raise SystemExit(f"unknown mode:{mode}")
