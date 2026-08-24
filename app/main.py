"""FastAPI 应用入口：创建应用、注册中间件/路由/异常处理器、启动服务。

★ 整个服务的组装线：配置 → 日志 → 中间件 → 路由 → 异常兜底，都在 create_app() 里按顺序完成。
"""

from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api import query_router, resources_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, register_request_logging_middleware
from engine.harness.caller import build_default_caller_resolver
from engine.harness.thread import ThreadCheckpointManager
from engine.harness.adapters import RAGToolAdapter
from engine.phase4b.task_boundary import TaskBoundary
from engine.rag.answer_flow import RAGAnswerFlow
from engine.rag.enterprise_generation import make_qwen_evidence_composer
from engine.rag.enterprise_product_runtime import (
    EnterpriseProductRuntime,
    EnterpriseProductRuntimeConfig,
    load_enterprise_product_runtime,
)
from engine.rag.retrieval import RetrievalAdapterError
from engine.rag.release import ReleaseError, load_active_release


logger = logging.getLogger(__name__)


def _unavailable_rag_status(*, mode: str, reason_code: str) -> dict[str, object]:
    """构造不含路径、key 或异常正文的 readiness 失败投影。"""

    return {
        "status": "unavailable",
        "retrieval_mode": mode,
        "reason_code": reason_code,
        "runtime_identity": None,
    }


def _lifespan(settings: Settings):
    """创建应用级 lifespan；重型 Enterprise runtime 只加载一次并成对释放。"""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Eval/合同测试会在进入 TestClient 前显式注入 factory。lifespan 只承认这条深 seam，
        # 不猜测请求体；退出后仍由注入方恢复自己的 factory。
        if getattr(application.state, "rag_tool_factory", None) is not None:
            previous_status = application.state.rag_runtime_status
            application.state.rag_runtime_status = {
                "status": "override",
                "retrieval_mode": "explicit_runtime_override",
                "reason_code": None,
                "runtime_identity": None,
            }
            try:
                yield
            finally:
                application.state.rag_runtime_status = previous_status
            return

        product: EnterpriseProductRuntime | None = None
        installed_factory = None
        config = EnterpriseProductRuntimeConfig.from_settings(settings)
        mode = config.retrieval_mode.strip().lower() or "semantic"
        try:
            product = load_enterprise_product_runtime(config=config)
            # semantic resolver 已要求同一个 key 用于 query embedding；显式 lexical 仍需在
            # ready 前补齐 Qwen Composer，不能让“检索可用”冒充完整产品 RAG 可用。
            if not settings.dashscope_api_key:
                raise RetrievalAdapterError(
                    "enterprise_rag_generation_not_configured", "DASHSCOPE_API_KEY is required"
                )

            def product_rag_tool_factory() -> RAGToolAdapter:
                """每请求新建轻量 Composer；共享的只有只读 profile/SQLite/Milvus runtime。"""

                assert product is not None
                composer = make_qwen_evidence_composer(
                    api_key=settings.dashscope_api_key,
                    base_url=settings.dashscope_base_url,
                    model=settings.qwen_model or "qwen3.7-plus",
                    timeout=settings.llm_timeout_seconds,
                )
                flow = RAGAnswerFlow(
                    knowledge_tool=product.runtime.knowledge_tool(),
                    composer=composer,
                    active_loader=product.runtime.active_loader,
                    retrieval_snapshot=product.identity.safe_projection(),
                )
                return RAGToolAdapter(
                    answer_flow=flow,
                    knowledge_runtime_kind="external_profile",
                )

            installed_factory = product_rag_tool_factory
            application.state.rag_tool_factory = installed_factory
            application.state.rag_runtime_status = {
                "status": "ready",
                "retrieval_mode": product.identity.retrieval_mode,
                "reason_code": None,
                "runtime_identity": product.identity.safe_projection(),
            }
            logger.info(
                "Enterprise RAG ready: mode=%s adapter=%s collection=%s semantic=%s",
                product.identity.retrieval_mode,
                product.identity.retrieval_adapter_identity,
                product.identity.milvus_collection or "not-applicable",
                (product.identity.semantic_identity or "not-applicable")[:12],
            )
        except Exception as exc:
            reason = (
                exc.reason_code
                if isinstance(exc, RetrievalAdapterError)
                else "enterprise_rag_runtime_unavailable"
            )
            application.state.rag_runtime_status = _unavailable_rag_status(
                mode=mode,
                reason_code=reason,
            )
            # 只记录异常类型和稳定 reason，避免本机 profile 路径进入公共日志。
            logger.warning(
                "Enterprise RAG unavailable: reason=%s type=%s",
                reason,
                type(exc).__name__,
            )

        try:
            yield
        finally:
            if installed_factory is not None and application.state.rag_tool_factory is installed_factory:
                application.state.rag_tool_factory = None
            if product is not None:
                product.close()

    return lifespan


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


def create_app(settings_override: Settings | None = None) -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    ★ 按顺序完成：读取配置 → 创建 app → 注册日志中间件 → 注册路由 → 注册异常兜底。
    这个函数是服务启动的唯一组装入口。
    """
    # 步骤 1：读取配置 =======================================================================
    # settings 是整个应用的配置对象，后续数据库、LLM、日志都会从这里取值。
    settings = settings_override or get_settings()
    configure_logging()

    # 步骤 2：创建 FastAPI 应用 ==============================================================
    # FastAPI 实例可以理解成“Web 服务总入口”，路由都会挂在这个对象上。
    application = FastAPI(
        title="DataPilot",
        description="Enterprise data analysis agent API.",
        version="0.1.0",
        lifespan=_lifespan(settings),
    )
    # ★ G-M35-1：只有明确 local/demo/test 环境才拥有 fixture resolver；其他环境保持 None，
    # 由 Harness 在 Tool 前失败关闭，绝不把请求体 user_role 当成生产身份。
    application.state.caller_resolver = build_default_caller_resolver(settings.app_env)
    # ★ M36 方案 A：应用生命周期持有唯一进程内 manager；endpoint 只能调用其深 interface，
    # 不能自己维护字典。服务重启会明确丢失 pending thread，不伪装成持久会话。
    application.state.thread_checkpoint_manager = ThreadCheckpointManager(
        ttl_seconds=settings.thread_checkpoint_ttl_seconds
    )
    application.state.task_boundary = TaskBoundary(ttl_seconds=settings.thread_checkpoint_ttl_seconds)
    # M44A：lifespan 在配置闭合时注入 Enterprise product factory；None 表示 fail-closed，
    # endpoint 不再构造业务小语料。Eval/测试仍可在进入 lifespan 前显式覆盖深 seam。
    application.state.rag_tool_factory = None
    # M44：task business requirement 的可信 registry seam。它与普通 API 的 Enterprise
    # 默认完全分离，不能由请求体选择；测试可显式替换 factory 但不能改 scope。
    application.state.business_rag_tool_factory = lambda: RAGToolAdapter()
    try:
        _pointer, business_bundle = load_active_release()
        application.state.business_rag_runtime_identity = f"business-release:{business_bundle.release_identity}"
    except ReleaseError:
        application.state.business_rag_runtime_identity = "business-release:unavailable"
    application.state.rag_runtime_status = _unavailable_rag_status(
        mode=settings.enterprise_rag_retrieval_mode,
        reason_code="enterprise_rag_lifespan_not_started",
    )
    # M43 deterministic rehearsal seam；请求体不能选择或替换 Tool。
    application.state.sql_tool_factory = None
    # 仅供显式 Eval 临时注入 Router seam；None 时普通 API 仍使用 Harness 的 deterministic 默认。
    application.state.harness_router = None
    register_request_logging_middleware(application)
    register_exception_handlers(application)
    application.include_router(resources_router)
    application.include_router(query_router)

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """健康检查接口：只回答服务是否活着，不依赖数据库或外部模型。"""
        return {"status": "ok"}

    @application.get("/health/rag", tags=["system"])
    def rag_health() -> JSONResponse:
        """返回 Enterprise RAG readiness；unavailable 不影响 SQL 服务的 liveness。"""

        status = dict(application.state.rag_runtime_status)
        return JSONResponse(
            status_code=200 if status.get("status") in {"ready", "override"} else 503,
            content=status,
        )

    @application.get("/config", tags=["system"], include_in_schema=False)
    def config_snapshot() -> dict[str, str]:
        """调试用配置快照：只返回非敏感信息，避免 API key、数据库密码泄露。"""
        return {
            "app_env": settings.app_env,
            "database_url": redact_database_url(settings.database_url),
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "enterprise_rag_retrieval_mode": settings.enterprise_rag_retrieval_mode,
            "enterprise_rag_status": str(application.state.rag_runtime_status.get("status")),
        }

    return application


app = create_app()
