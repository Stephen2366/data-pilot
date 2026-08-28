"""以 M50 演示配置启动 FastAPI，并把 Trace 固定写入模块临时目录。

本入口从当前 MySQL URL 只替换 database 段为 ``datapilot_demo``，避免把密码拼进 shell
命令或修改 `.env`。它只增加目标库护栏和 Trace 路径，不改模型、RAG strategy、caller、
task boundary 或 FastAPI 业务行为。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Generator

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import create_app
try:
    from scripts.prepare_m50_demo import TARGET_DATABASE
except ModuleNotFoundError:
    # 同时支持 runbook 中常见的 `python scripts/...py` 与 `python -m scripts...`。
    from prepare_m50_demo import TARGET_DATABASE


def build_demo_app(*, rag_strategy: str = "pipeline", trace_path: Path | None = None):
    """在创建 engine/runtime 前确认服务只连接独立 demo 数据库。"""

    configured = get_settings()
    source = make_url(configured.database_url)
    if source.get_backend_name() != "mysql":
        raise RuntimeError("m50_demo_api_requires_mysql")
    demo_url = source.set(database=TARGET_DATABASE).render_as_string(hide_password=False)
    # 显式字段优先于 .env 的 DATABASE_URL，其他 API key/model/timeout 仍按项目配置读取。
    settings = Settings(DATABASE_URL=demo_url, PHASE4B_RAG_STRATEGY=rag_strategy)
    database = make_url(settings.database_url).database
    if database != TARGET_DATABASE:
        raise RuntimeError(f"m50_demo_api_refuses_database:{database}")
    application = create_app(settings)
    # ★ create_app(settings) 会用传入配置组装 durable task boundary，但 FastAPI 的 get_db
    # 依赖来自模块导入期全局 SessionLocal。演示启动器必须像真实 Probe 一样显式 override，
    # 才能保证 task checkpoint 与 SQL business query 都落在同一个 datapilot_demo 世界。
    demo_engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    demo_sessions = sessionmaker(bind=demo_engine, expire_on_commit=False)

    def override_db() -> Generator[Session, None, None]:
        with demo_sessions() as session:
            yield session

    application.dependency_overrides[get_db] = override_db
    application.state.m50_demo_engine = demo_engine
    trace_path = trace_path or Path(os.environ.get("M50_TRACE_PATH", ".agent_work/temp/m50/live-api/trace.jsonl"))
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    application.state.trace_path = trace_path
    return application


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the guarded M50 demo FastAPI application.")
    parser.add_argument("--rag-strategy", choices=("pipeline", "subgraph"), default="pipeline")
    parser.add_argument("--trace-path", type=Path, default=Path(".agent_work/temp/m50/live-api/trace.jsonl"))
    parser.add_argument("--proxy", help="Optional operator-controlled HTTP/HTTPS proxy for provider transport.")
    args = parser.parse_args()
    if args.proxy:
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy
    uvicorn.run(
        build_demo_app(rag_strategy=args.rag_strategy, trace_path=args.trace_path),
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
