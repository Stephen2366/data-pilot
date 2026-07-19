"""API 路由聚合入口：把各业务 router 暴露给 app.main 统一注册。"""

from app.api.resources import router as resources_router
from app.api.query import router as query_router

__all__ = ["query_router", "resources_router"]
