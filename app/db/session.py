"""数据库连接管理：Engine 构建 + FastAPI 依赖注入式的 Session 生命周期。

★ 每个请求通过 get_db() 获取独立 Session，请求结束自动关闭，
类比 Java Spring 中每个请求绑定一个 EntityManager。
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(database_url: str) -> Engine:
    """Create the shared SQLAlchemy engine for application requests.

    ★ `pool_pre_ping=True` 会在连接交给业务代码前先探活。MySQL 连接空闲太久时
    可能被服务端断开，pre-ping 可以避免请求拿到一条已经失效的连接。
    """

    return create_engine(database_url, pool_pre_ping=True)


settings = get_settings()
engine = build_engine(settings.database_url)

# SessionLocal 是“会话工厂”：每个请求从这里拿一个独立 Session，用完立即关闭。
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：为每个请求提供一个独立的数据库 Session。

    ★ yield 写法是 FastAPI 依赖的“前置 + 后置”模式：yield 之前相当于请求开始时借出
    连接，finally 保证请求无论成功还是抛异常都归还连接（类比 Java 的 try-with-resources）。
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
