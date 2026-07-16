from fastapi import FastAPI

from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="DataPilot",
        description="Enterprise data analysis agent API.",
        version="0.1.0",
    )

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/config", tags=["system"], include_in_schema=False)
    def config_snapshot() -> dict[str, str]:
        return {
            "app_env": settings.app_env,
            "database_url": settings.database_url,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
        }

    return application


app = create_app()
