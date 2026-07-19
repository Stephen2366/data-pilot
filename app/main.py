"""FastAPI 应用入口：创建应用、注册中间件/路由/异常处理器、启动服务。

★ 整个服务的组装线：配置 → 日志 → 中间件 → 路由 → 异常兜底，都在 create_app() 里按顺序完成。
"""

from fastapi import FastAPI

from app.api import resources_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, register_request_logging_middleware


def redact_database_url(database_url: str) -> str:
    """Hide the password part of a SQLAlchemy database URL.

    ★ 新手理解：数据库连接串里通常有账号密码，调试接口可以展示“连到哪里”，
    但不能把密码也展示出去，所以这里把 `user:password@host` 中的 password 替换成 `***`。
    """

    if "://" not in database_url or "@" not in database_url:
        return database_url

    scheme, rest = database_url.split("://", 1)
    credentials, host_and_path = rest.split("@", 1)

    if ":" not in credentials:
        return database_url

    username, _password = credentials.split(":", 1)
    return f"{scheme}://{username}:***@{host_and_path}"


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    ★ 按顺序完成：读取配置 → 创建 app → 注册日志中间件 → 注册路由 → 注册异常兜底。
    这个函数是服务启动的唯一组装入口。
    """
    # 步骤 1：读取配置 =======================================================================
    # settings 是整个应用的配置对象，后续数据库、LLM、日志都会从这里取值。
    settings = get_settings()
    configure_logging()

    # 步骤 2：创建 FastAPI 应用 ==============================================================
    # FastAPI 实例可以理解成“Web 服务总入口”，路由都会挂在这个对象上。
    application = FastAPI(
        title="DataPilot",
        description="Enterprise data analysis agent API.",
        version="0.1.0",
    )
    register_request_logging_middleware(application)
    register_exception_handlers(application)
    application.include_router(resources_router)

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """健康检查接口：只回答服务是否活着，不依赖数据库或外部模型。"""
        return {"status": "ok"}

    @application.get("/config", tags=["system"], include_in_schema=False)
    def config_snapshot() -> dict[str, str]:
        """调试用配置快照：只返回非敏感信息，避免 API key、数据库密码泄露。"""
        return {
            "app_env": settings.app_env,
            "database_url": redact_database_url(settings.database_url),
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
        }

    return application


app = create_app()
