"""M4 NL2SQL smoke：真实调用 `/api/query` 的 LLM 生成路径和增强 SQL Guard。

用法（项目根目录执行）：

    python scripts/smoke_m4_nl2sql.py

★ 这个脚本默认走配置里的 DeepSeek 主路径，不使用假 LLM。它用内存 SQLite 承载 M1 seed
数据，避免 smoke 写入 MySQL 主库；prompt 快照和结果摘要写入 `.agent_work/temp/`。
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
from engine.nl2sql.prompt import build_sql_prompt
from engine.nl2sql.schema_loader import load_domain_schema
from scripts.seed_data import seed_database


@dataclass(frozen=True)
class SmokeCase:
    """M4 simple SQL smoke 用例。"""

    case_id: str
    question: str
    user_role: str
    expected_columns: tuple[str, ...]
    expected_text: str


CASES: tuple[SmokeCase, ...] = (
    SmokeCase("sql_001", "查询 active 商品列表前 10 条", "ops", ("product_name", "category", "status"), "active"),
    SmokeCase("sql_002", "查询 Electronics 类目下有哪些商品", "ops", ("product_name", "category"), "Electronics"),
    SmokeCase("sql_003", "查询 2026 年 6 月已支付订单", "ops", ("order_no", "order_amount", "paid_at"), "2026-06"),
    SmokeCase("sql_004", "查询 quality_issue 的退款记录", "ops", ("refund_no", "refund_reason"), "quality_issue"),
    SmokeCase("sql_005", "查询待处理工单列表", "customer_service", ("ticket_no", "status"), "pending"),
    SmokeCase("sql_006", "查询 Mobile App 渠道基本信息", "ops", ("channel_name", "channel_type"), "Mobile App"),
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


def _write_prompt_snapshots(output_path: Path) -> None:
    """为 6 条 simple SQL 问题保存 prompt 快照。"""

    domain_schema = load_domain_schema()
    lines = ["# M4 Prompt Snapshots", ""]
    for case in CASES:
        prompt = build_sql_prompt(
            question=case.question,
            user_role=case.user_role,
            domain_schema=domain_schema,
        )
        lines.append(f"## {case.case_id} {case.question}")
        lines.append("")
        lines.append("```text")
        lines.append(prompt.rstrip())
        lines.append("```")
        lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _case_passed(body: dict[str, Any], case: SmokeCase) -> tuple[bool, str]:
    """按 M4 simple SQL 正确性口径检查单条响应。"""

    if body.get("safety_status") != "passed":
        return False, f"blocked={body.get('blocked_reason')}"
    missing_columns = [column for column in case.expected_columns if column not in body.get("columns", [])]
    if missing_columns:
        return False, f"missing_columns={missing_columns}"
    if case.expected_text not in str(body):
        return False, f"missing_text={case.expected_text}"
    return True, "ok"


def main() -> int:
    """执行 M4 smoke，并要求 6 条 simple SQL 至少 5 条通过。"""

    # 步骤 1：先写 prompt 快照，方便人工回看 LLM 到底看到了哪些表、字段和约束。
    temp_dir = PROJECT_ROOT / ".agent_work" / "temp"
    prompt_path = temp_dir / "prompt-snapshots.md"
    summary_path = temp_dir / "m4-smoke.md"
    _write_prompt_snapshots(prompt_path)

    # 步骤 2：用内存库跑 seed，避免 smoke 对 MySQL 开发库产生写入副作用。
    engine = _prepare_sqlite_seed()

    def override_get_db():
        """把正式数据库依赖替换成内存 SQLite，方便 smoke 重复执行。"""

        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    from fastapi.testclient import TestClient  # noqa: WPS433

    client = TestClient(app)
    lines = ["# M4 NL2SQL Smoke 摘要", "", f"- prompt_snapshots={prompt_path}", ""]
    passed_count = 0
    try:
        # 步骤 3：逐条通过真实 `/api/query` 调用 DeepSeek 路径，并记录首行结果。
        for case in CASES:
            response = client.post(
                "/api/query",
                json={"question": case.question, "user_role": case.user_role},
            )
            body = response.json()
            passed, reason = _case_passed(body, case)
            passed_count += int(passed)
            first_row = body["rows"][0] if body.get("rows") else {}
            line = (
                f"- {case.case_id}: passed={passed}, reason={reason}, status={response.status_code}, "
                f"safety={body.get('safety_status')}, columns={body.get('columns')}, "
                f"first_row={first_row}, trace_id={body.get('trace_id')}"
            )
            print(line)
            lines.append(line)
            lines.append(f"  sql={body.get('sql')}")
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)

    # 步骤 4：把摘要持久化到临时目录，finish-module / accept-module 可以直接引用。
    lines.append("")
    lines.append(f"- simple_sql_passed={passed_count}/6")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"summary={summary_path}")
    print(f"prompt_snapshots={prompt_path}")
    return 0 if passed_count >= 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
