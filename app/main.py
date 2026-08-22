"""FastAPI 应用入口：创建应用、注册中间件/路由/异常处理器、启动服务。

★ 整个服务的组装线：配置 → 日志 → 中间件 → 路由 → 异常兜底，都在 create_app() 里按顺序完成。
"""

from fastapi import FastAPI

from app.api import query_router, resources_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, register_request_logging_middleware
from engine.harness.caller import build_default_caller_resolver
from engine.harness.thread import ThreadCheckpointManager


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
    # ★ G-M35-1：只有明确 local/demo/test 环境才拥有 fixture resolver；其他环境保持 None，
    # 由 Harness 在 Tool 前失败关闭，绝不把请求体 user_role 当成生产身份。
    application.state.caller_resolver = build_default_caller_resolver(settings.app_env)
    # ★ M36 方案 A：应用生命周期持有唯一进程内 manager；endpoint 只能调用其深 interface，
    # 不能自己维护字典。服务重启会明确丢失 pending thread，不伪装成持久会话。
    application.state.thread_checkpoint_manager = ThreadCheckpointManager(
        ttl_seconds=settings.thread_checkpoint_ttl_seconds
    )
    # M41：普通请求保持 None，仍由 endpoint 构造 deterministic RAG Tool。只有受控 Eval
    # 在进程内临时注入 factory；请求体没有字段可以选择 Composer 或提升运行权限。
    application.state.rag_tool_factory = None
    register_request_logging_middleware(application)
    register_exception_handlers(application)
    application.include_router(resources_router)
    application.include_router(query_router)

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
