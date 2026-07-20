"""M5 AgentResponse smoke：验证扩展响应、SQL Tool、Trace JSONL 和基础图表 spec。

用法（项目根目录执行）：

    python scripts/smoke_m5_agent_response.py

★ 本脚本仍使用内存 SQLite + M1 确定性 seed，不碰 MySQL 主库；它把 trace 写到
`.agent_work/temp/m5-traces.jsonl`，把人工验收摘要写到 `.agent_work/temp/m5-smoke.md`。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# 把项目根目录加入 sys.path，保证从 scripts/ 直接运行时也能导入 app / engine。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from scripts.seed_data import seed_database


@dataclass(frozen=True)
class SmokeCase:
    """M5 smoke 用例定义。"""

    case_id: str
    question: str
    user_role: str
    expected_safety: str
    expected_chart_mark: str | None
    expected_chart_field: str | None


CASES: tuple[SmokeCase, ...] = (
    SmokeCase("chart_channel_orders", "各渠道订单量是多少？", "ops", "passed", "bar", "order_count"),
    SmokeCase("chart_refund_rate", "2026年6月退款率最高的商品是什么？", "ops", "passed", "bar", "refund_rate"),
    SmokeCase("chart_june_gmv", "2026年6月本月GMV是多少？", "ops", "passed", "bar", "gmv"),
    SmokeCase("blocked_drop", "DROP TABLE orders", "admin", "blocked", None, None),
)


def _prepare_sqlite_seed() -> Any:
    """创建带 seed 数据的内存 SQLite engine。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)
    return engine


def _chart_field(body: dict[str, Any]) -> str | None:
    """从 chart_spec 中取出主业务指标字段，兼容普通柱状图、横向柱状图和单指标图。"""

    chart_spec = body.get("chart_spec")
    if not chart_spec:
        return None
    data_values = (chart_spec.get("data") or {}).get("values") or []
    if data_values and data_values[0].get("metric_name"):
        return data_values[0]["metric_name"]
    encoding = chart_spec.get("encoding") or {}
    y_field = (encoding.get("y") or {}).get("field")
    x_field = (encoding.get("x") or {}).get("field")
    return y_field if y_field != "product_name" else x_field


def _case_passed(body: dict[str, Any], case: SmokeCase) -> tuple[bool, str]:
    """按 M5 验收口径检查响应字段、图表和 tool trace。"""

    required_fields = {
        "route",
        "answer",
        "tables_used",
        "docs_used",
        "chart_spec",
        "safety_status",
        "cost",
        "tool_calls",
        "trace_id",
    }
    missing = sorted(required_fields - body.keys())
    if missing:
        return False, f"missing_fields={missing}"
    if body["safety_status"] != case.expected_safety:
        return False, f"safety={body['safety_status']}"
    if not body["tool_calls"]:
        return False, "tool_calls_empty"
    if body["cost"]["latency_ms"] < 0:
        return False, "negative_latency"

    chart_spec = body.get("chart_spec")
    actual_mark = chart_spec.get("mark") if chart_spec else None
    actual_field = _chart_field(body)
    if actual_mark != case.expected_chart_mark:
        return False, f"chart_mark={actual_mark}"
    if case.expected_chart_field and case.expected_chart_field != actual_field:
        return False, f"chart_field={actual_field}"
    return True, "ok"


def main() -> int:
    """执行 M5 smoke，并要求 4 条用例全部通过。"""

    temp_dir = PROJECT_ROOT / ".agent_work" / "temp"
    trace_path = temp_dir / "m5-traces.jsonl"
    summary_path = temp_dir / "m5-smoke.md"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")

    # 步骤 1：准备内存库和 FastAPI 依赖覆盖 ------------------------------------------------
    engine = _prepare_sqlite_seed()

    def override_get_db():
        """把正式数据库依赖替换成内存 SQLite，方便 smoke 重复执行。"""

        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path

    from fastapi.testclient import TestClient  # noqa: WPS433

    client = TestClient(app)
    lines = ["# M5 AgentResponse Smoke 摘要", "", f"- trace_path={trace_path}", ""]
    passed_count = 0
    try:
        # 步骤 2：逐条调用真实 `/api/query`，检查响应契约和图表字段。-------------------------
        for case in CASES:
            response = client.post(
                "/api/query",
                json={"question": case.question, "user_role": case.user_role},
            )
            body = response.json()
            passed, reason = _case_passed(body, case)
            passed_count += int(passed)
            line = (
                f"- {case.case_id}: passed={passed}, reason={reason}, status={response.status_code}, "
                f"safety={body.get('safety_status')}, chart_mark={body.get('chart_spec', {}).get('mark') if body.get('chart_spec') else None}, "
                f"chart_field={_chart_field(body)}, tool={body.get('tool_calls', [{}])[0].get('tool_name')}, "
                f"latency_ms={body.get('cost', {}).get('latency_ms')}, trace_id={body.get('trace_id')}"
            )
            print(line)
            lines.append(line)
            lines.append(f"  tables_used={body.get('tables_used')} sql={body.get('sql')}")
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "trace_path"):
            delattr(app.state, "trace_path")
        Base.metadata.drop_all(engine)

    # 步骤 3：写入摘要，finish-module / accept-module 可以直接引用。------------------------
    trace_lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    lines.append("")
    lines.append(f"- passed={passed_count}/{len(CASES)}")
    lines.append(f"- trace_lines={len(trace_lines)}")
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"summary={summary_path}")
    print(f"trace_path={trace_path}")
    return 0 if passed_count == len(CASES) and len(trace_lines) == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
