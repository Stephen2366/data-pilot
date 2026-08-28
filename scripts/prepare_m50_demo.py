"""准备或只读核验 M50 独立演示数据库 ``datapilot_demo``。

用法：

    python -m scripts.prepare_m50_demo preflight --confirm-database datapilot_demo
    python -m scripts.prepare_m50_demo prepare --confirm-database datapilot_demo

★ ``prepare`` 会重建目标库中的表和业务数据，因此必须显式提交精确库名。脚本从当前
MySQL URL 只替换 database 段，永远拒绝 dev/test/prod/空名称；Web 页面没有调用入口。
``preflight`` 只读核验 migration、7/8 月 oracle 和 task 临时行数，零 provider。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings

TARGET_DATABASE = "datapilot_demo"
ALEMBIC_HEAD = "20260827_0005"
OUTPUT_DIR = Path(".agent_work/temp/m50/demo-prepare")


def resolve_demo_url(configured_url: str, confirmed_database: str) -> URL:
    """在任何连接/DDL 前冻结唯一目标，防止“变量写错后删错库”。"""

    source = make_url(configured_url)
    if source.get_backend_name() != "mysql":
        raise ValueError("m50_demo_requires_mysql")
    if confirmed_database != TARGET_DATABASE:
        raise ValueError("m50_demo_confirmation_mismatch")
    target = source.set(database=TARGET_DATABASE)
    if target.database != TARGET_DATABASE:
        raise ValueError("m50_demo_target_mismatch")
    return target


def _facts(target_url: str) -> dict[str, Any]:
    """从目标库读取演示 Gate；不调用模型、embedding、Milvus 或业务 Tool。"""

    engine = create_engine(target_url, pool_pre_ping=True, future=True)
    with engine.connect() as connection:
        migration = connection.scalar(text("SELECT version_num FROM alembic_version"))
        amounts = connection.execute(text(
            "SELECT DATE_FORMAT(processed_at, '%Y-%m') AS month, "
            "CAST(SUM(refund_amount) AS DECIMAL(18,2)) AS amount "
            "FROM refunds WHERE refund_status='completed' "
            "AND processed_at >= '2026-07-01' AND processed_at < '2026-09-01' "
            "GROUP BY DATE_FORMAT(processed_at, '%Y-%m') ORDER BY month"
        )).all()
        checkpoints = int(connection.scalar(text("SELECT COUNT(*) FROM agent_task_checkpoints")) or 0)
        events = int(connection.scalar(text("SELECT COUNT(*) FROM agent_task_events")) or 0)
    observed = {str(month): str(amount) for month, amount in amounts}
    return {
        "database": TARGET_DATABASE,
        "migration": str(migration),
        "oracle": observed,
        "task_rows": {"checkpoints": checkpoints, "events": events},
        "provider_calls": 0,
        "ready": str(migration) == ALEMBIC_HEAD
        and observed == {"2026-07": "120000.00", "2026-08": "180000.00"}
        and checkpoints == 0
        and events == 0,
    }


def prepare(target: URL) -> dict[str, Any]:
    """只在已确认目标库重建 migration world 和 Phase 4B deterministic seed。"""

    # SQLAlchemy URL.set 的 None 表示“保留原值”，不是清空字段；连接系统库 mysql 才能
    # 在目标库尚不存在时安全执行 CREATE DATABASE。
    admin = target.set(database="mysql")
    with create_engine(admin, future=True).begin() as connection:
        connection.execute(text(f"CREATE DATABASE IF NOT EXISTS `{TARGET_DATABASE}` CHARACTER SET utf8mb4"))

    target_url = target.render_as_string(hide_password=False)
    engine = create_engine(target_url, future=True)
    # MySQL DDL 不可事务回滚；所以目标必须在上方白名单门闭合后才允许来到这里。
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in inspect(engine).get_table_names():
            connection.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    os.environ["DATABASE_URL"] = target_url
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), ALEMBIC_HEAD)

    import scripts.seed_data as seed_module

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seed_module.SEED_SUMMARY_PATH = OUTPUT_DIR / "seed-summary.md"
    with Session(engine) as session:
        seed_summary = seed_module.seed_database(session, reset_existing=True, profile_alias="phase4b")
    facts = _facts(target_url)
    return {
        "operation": "prepare",
        "seed_profile": seed_summary["seed_profile"],
        "phase4b_facts": seed_summary["phase4b_facts"],
        **facts,
    }


def main() -> None:
    """解析命令后先做字符串护栏，再执行 prepare/preflight。"""

    parser = argparse.ArgumentParser(description="Prepare the isolated M50 DataPilot demo database.")
    parser.add_argument("mode", choices=("prepare", "preflight"))
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()

    target = resolve_demo_url(get_settings().database_url, args.confirm_database)
    target_url = target.render_as_string(hide_password=False)
    result = prepare(target) if args.mode == "prepare" else {"operation": "preflight", **_facts(target_url)}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{args.mode}-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
