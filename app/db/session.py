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
    """FastAPI dependency that provides one database Session per request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
