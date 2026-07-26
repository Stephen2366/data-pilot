"""应用配置模块：统一从环境变量/.env 读取所有配置项。

★ 业务代码只从 Settings 类拿配置，不在各处散落 os.environ 读取，
排查配置问题时只需关注这一个文件。
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    ★ 新手理解：这里相当于项目的“配置入口”。代码只从这个类拿配置，
    不在业务代码里到处读 `.env`，后面排查问题会更集中。
    """

    # 基础运行配置 =============================================================================
    # Field(alias=...) 让 Python 字段名保持小写风格，同时能读取大写环境变量。
    app_env: str = Field(default="local", alias="APP_ENV")
    # ★ 默认值仅作占位兜底，实际连接串以 .env 的 DATABASE_URL 为准（开发库为 datapilot_dev）。
    database_url: str = Field(
        default=("mysql+pymysql://datapilot_user:change-me@127.0.0.1:3306/" "datapilot_dev?charset=utf8mb4"),
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # LLM 通用配置 =============================================================================
    # LLM 是大语言模型。这里先保留一个通用入口，后续 generator 可以按 provider 选择模型。
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    llm_model: str = Field(default="mock-sql-generator", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")

    # 常用模型供应商配置 ========================================================================
    # 当前只建模常用的 DeepSeek 和 SiliconFlow；其他供应商暂时交给 extra="ignore" 忽略。
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="", alias="DEEPSEEK_BASE_URL")
    siliconflow_api_key: str = Field(default="", alias="SILICONFLOW_API_KEY")
    siliconflow_base_url: str = Field(default="", alias="SILICONFLOW_BASE_URL")

    # Schema Retrieval 配置 ===================================================================
    # 默认仍走纯本地 deterministic in-memory；Milvus / SiliconFlow 必须显式开启。
    schema_vector_backend: str = Field(default="inmemory", alias="SCHEMA_VECTOR_BACKEND")
    schema_embedding_provider: str = Field(default="deterministic", alias="SCHEMA_EMBEDDING_PROVIDER")
    milvus_collection: str = Field(default="datapilot_schema_docs", alias="MILVUS_COLLECTION")
    milvus_uri: str = Field(default="http://127.0.0.1:19530", alias="MILVUS_URI")
    milvus_reset_collection: bool = Field(default=False, alias="MILVUS_RESET_COLLECTION")
    siliconflow_embedding_model: str = Field(default="BAAI/bge-m3", alias="SILICONFLOW_EMBEDDING_MODEL")
    siliconflow_embedding_dimensions: int | None = Field(default=None, alias="SILICONFLOW_EMBEDDING_DIMENSIONS")

    # 可观测性配置 =============================================================================
    # LangSmith 用来记录/观察 LLM 调用链路，后续调试 Agent 时会很有用。
    langsmith_tracing: str = Field(default="false", alias="LANGSMITH_TRACING")
    langsmith_endpoint: str = Field(default="", alias="LANGSMITH_ENDPOINT")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="", alias="LANGSMITH_PROJECT")

    # ★ extra="ignore" 表示 `.env` 里多出来的字段先忽略，不让本地私有配置拖垮服务启动。
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """返回全局唯一的 Settings 实例（通过 lru_cache 保证单例）。

    ★ lru_cache 让 Settings 只创建一次，避免每次请求都重新读取 .env 文件。
    """
    return Settings()
