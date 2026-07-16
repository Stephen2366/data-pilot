from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = Field(default="local", alias="APP_ENV")
    database_url: str = Field(
        default=(
            "mysql+pymysql://datapilot_user:change-me@127.0.0.1:3306/"
            "datapilot?charset=utf8mb4"
        ),
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    llm_model: str = Field(default="mock-sql-generator", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="", alias="DEEPSEEK_BASE_URL")
    siliconflow_api_key: str = Field(default="", alias="SILICONFLOW_API_KEY")
    siliconflow_base_url: str = Field(default="", alias="SILICONFLOW_BASE_URL")
    langsmith_tracing: str = Field(default="false", alias="LANGSMITH_TRACING")
    langsmith_endpoint: str = Field(default="", alias="LANGSMITH_ENDPOINT")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="", alias="LANGSMITH_PROJECT")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
