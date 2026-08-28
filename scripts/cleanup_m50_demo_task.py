"""按 Trace 中的不可逆 task safe ref 清理 M50 Probe synthetic 行。

真实 task id 不落 MySQL；当浏览器 lineage 已因基础设施失败不再继续时，Probe cleanup 只能
使用 Trace 公共 ``task_safe_ref`` 对账。脚本固定连接 ``datapilot_demo``，先解析唯一 task_key，
再在一个事务中删除该 task 的 event/checkpoint；找不到或命中多 task 时失败关闭。
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base  # noqa: F401  # 先完成聚合模型注册，避免 app.models 循环导入。
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
try:
    # `python -m scripts.cleanup_m50_demo_task` 从仓库根目录解析 package。
    from scripts.prepare_m50_demo import TARGET_DATABASE
except ModuleNotFoundError:
    # 也支持按文件直接执行，避免收工 runbook 因入口形式不同而在清理前失败。
    from prepare_m50_demo import TARGET_DATABASE


def main() -> None:
    """只删除一个经 safe ref 精确定位的 synthetic task，并要求删除后 demo task 表归零。"""

    parser = argparse.ArgumentParser(description="Cleanup one exact M50 demo synthetic task.")
    parser.add_argument("--task-safe-ref", required=True)
    args = parser.parse_args()
    if not args.task_safe_ref.startswith("task:") or len(args.task_safe_ref) != 69:
        raise SystemExit("invalid_task_safe_ref")

    source = make_url(get_settings().database_url)
    target = source.set(database=TARGET_DATABASE)
    if source.get_backend_name() != "mysql" or target.database != TARGET_DATABASE:
        raise SystemExit("m50_demo_cleanup_target_mismatch")
    engine = create_engine(target.render_as_string(hide_password=False), future=True)
    with Session(engine) as session, session.begin():
        keys = session.scalars(
            select(AgentTaskCheckpoint.task_key).where(
                AgentTaskCheckpoint.task_safe_ref == args.task_safe_ref
            )
        ).all()
        if len(keys) != 1:
            raise RuntimeError(f"m50_demo_cleanup_expected_one_task:observed={len(keys)}")
        task_key = keys[0]
        events_deleted = session.execute(
            delete(AgentTaskEvent).where(AgentTaskEvent.task_key == task_key)
        ).rowcount
        checkpoints_deleted = session.execute(
            delete(AgentTaskCheckpoint).where(AgentTaskCheckpoint.task_key == task_key)
        ).rowcount

    with Session(engine) as session:
        remaining = {
            "checkpoints": session.scalar(select(func.count()).select_from(AgentTaskCheckpoint)) or 0,
            "events": session.scalar(select(func.count()).select_from(AgentTaskEvent)) or 0,
        }
    print(json.dumps({
        "database": TARGET_DATABASE,
        "task_safe_ref": args.task_safe_ref,
        "deleted": {"checkpoints": checkpoints_deleted, "events": events_deleted},
        "remaining": remaining,
    }, ensure_ascii=False, indent=2))
    if remaining != {"checkpoints": 0, "events": 0}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
