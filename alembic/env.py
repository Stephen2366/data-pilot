"""Alembic 迁移环境配置：连接数据库、注册 ORM metadata、切换离线/在线模式。

★ FastAPI 服务和 Alembic 迁移共用同一份 DATABASE_URL（通过 app.core.config.Settings），
避免"服务连 A 库、迁移连 B 库"的配置漂移事故。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base

config = context.config

# Alembic 自带日志配置会读取 alembic.ini；这里复用它，避免迁移时没有日志。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ★ Alembic autogenerate 会读取这里的 metadata，确认 7 张 ORM 表的最终结构。
target_metadata = Base.metadata


def _database_url() -> str:
    """从 FastAPI 相同的 Settings 对象读取 DATABASE_URL。

    ★ 这样 FastAPI 服务和 Alembic 迁移只维护一份 DATABASE_URL，避免"服务连 A 库，
    迁移连 B 库"的事故。
    """

    return get_settings().database_url


def run_migrations_offline() -> None:
    """离线模式运行迁移：不创建数据库 Engine，仅生成 SQL 脚本。"""

    # offline 模式只生成 SQL 文本，不真的连接数据库；适合审查迁移 SQL。
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式运行迁移：直连 MySQL 开发库执行 DDL。"""

    # online 模式会真实连接 MySQL 并执行 migration，是阶段二建表主路径。
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    # NullPool 表示 Alembic 用完连接就释放，不和 FastAPI 服务共享连接池。
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # compare_type=True 让 alembic check 能发现模型字段类型和数据库不一致。
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
