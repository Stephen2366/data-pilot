"""M3 v0 smoke 脚本：验证 `/api/query` 的模板 SQL 闭环和 SQL Guard 拦截。

用法（项目根目录执行）：

    python scripts/smoke_v0.py

★ smoke 的职责是给人工验收一份“实际输出摘要”。它使用 SQLite + M1 seed 数据，
不碰 MySQL 主库；输出摘要会写入 `.agent_work/temp/v0-smoke.md`。
"""

from __future__ import annotations

import sys
from pathlib import Path

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


engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)

with Session(engine) as session:
    seed_database(session, reset_existing=True)


def override_get_db():
    """把正式数据库依赖替换成内存 SQLite，方便 smoke 重复执行。"""

    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

from fastapi.testclient import TestClient  # noqa: E402


client = TestClient(app)

cases = [
    ("refund-rate", "2026年6月退款率最高的商品是什么？", "ops"),
    ("channel-orders", "各渠道订单量是多少？", "ops"),
    ("june-gmv", "2026年6月本月GMV是多少？", "ops"),
    ("top-refund-reason", "Top退款原因是什么？", "ops"),
    ("pending-high-tickets", "待处理高优先级工单有多少？", "customer_service"),
    ("dangerous-drop", "DROP TABLE orders", "admin"),
]

lines = ["# M3 v0 Smoke 摘要", ""]
for name, question, user_role in cases:
    response = client.post("/api/query", json={"question": question, "user_role": user_role})
    body = response.json()
    first_row = body["rows"][0] if body["rows"] else {}
    line = (
        f"- {name}: status={response.status_code}, safety={body['safety_status']}, "
        f"columns={body['columns']}, first_row={first_row}, trace_id={body['trace_id']}"
    )
    print(line)
    lines.append(line)

output_path = PROJECT_ROOT / ".agent_work" / "temp" / "v0-smoke.md"
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"summary={output_path}")

app.dependency_overrides.clear()
