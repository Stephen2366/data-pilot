"""M2 API smoke 脚本：8 个筛选组合 + 1 个非法分页，快速验证 4 类列表接口的行为契约。

用法（项目根目录执行）：

    python scripts/smoke_m2_api.py

★ 和 pytest 的分工：pytest 断言“必须对”，smoke 打印“实际长什么样”——人工扫一眼
status / total / trace_id 是否符合预期，属于 phase2-plan M2「模块验证命令」的一部分。
数据库用内存 SQLite + M1 确定性 seed，不碰 MySQL 主库，随时可重复执行。
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# 把项目根目录加进 sys.path：本文件位于 scripts/ 下，parents[1] 即项目根。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from scripts.seed_data import seed_database


# 内存 SQLite + StaticPool：所有连接复用同一个内存库（与 tests/test_m2_api.py 同一套路）。
engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)

# 灌入 M1 确定性 seed：保证 smoke 输出里的 total 每次一致，肉眼可比对。
with Session(engine) as session:
    seed_database(session, reset_existing=True)


def override_get_db():
    # 依赖覆盖：接口代码不改，把底层数据库整体换成上面的内存库。
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

from fastapi.testclient import TestClient  # noqa: E402


client = TestClient(app)

# 9 个用例 = 4 类接口 × 2 个筛选组合 + 1 个非法分页（应返回 422 + validation_error）。
cases = [
    ("products-electronics-active", "/api/products", {"category": "Electronics", "status": "active"}),
    ("products-saas-active", "/api/products", {"category": "SaaS", "status": "active"}),
    ("orders-june-mobile-paid", "/api/orders", {"paid_from": "2026-06-01T00:00:00", "paid_to": "2026-07-01T00:00:00", "channel_id": 1, "order_status": "paid"}),
    ("orders-may-cancelled", "/api/orders", {"paid_from": "2026-05-01T00:00:00", "paid_to": "2026-06-01T00:00:00", "order_status": "cancelled"}),
    ("refunds-quality-approved", "/api/refunds", {"refund_status": "approved", "refund_reason": "quality_issue"}),
    ("refunds-late-completed", "/api/refunds", {"refund_status": "completed", "refund_reason": "late_delivery"}),
    ("tickets-pending-high-refund", "/api/tickets", {"status": "pending", "priority": "high", "ticket_type": "refund"}),
    ("tickets-processing-low-shipping", "/api/tickets", {"status": "processing", "priority": "low", "ticket_type": "shipping"}),
    ("invalid-page", "/api/products", {"page": 0}),
]

for name, path, params in cases:
    response = client.get(path, params=params)
    body = response.json()
    trace_id = response.headers.get("x-trace-id")
    total = body.get("total", "-")
    code = body.get("code", "ok")
    print(f"{name}: status={response.status_code} total={total} code={code} trace_id={trace_id}")

app.dependency_overrides.clear()
