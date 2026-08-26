"""应用配置模块：统一从环境变量/.env 读取所有配置项。

★ 业务代码只从 Settings 类拿配置，不在各处散落 os.environ 读取，
排查配置问题时只需关注这一个文件。
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    # M36 只保存 pre-Tool pending clarification；15 分钟后失效，避免内存态变成长期会话仓库。
    thread_checkpoint_ttl_seconds: int = Field(default=900, gt=0, alias="THREAD_CHECKPOINT_TTL_SECONDS")

    # LLM 通用配置 =============================================================================
    # LLM 是大语言模型。这里先保留一个通用入口，后续 generator 可以按 provider 选择模型。
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    llm_model: str = Field(default="mock-sql-generator", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    # M25：45 秒仍是兼容默认；重试默认关闭，只在聚焦实验中显式开启。
    llm_timeout_seconds: float = Field(default=45.0, gt=0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=0, ge=0, alias="LLM_MAX_RETRIES")
    llm_retry_backoff_seconds: float = Field(default=1.0, ge=0, alias="LLM_RETRY_BACKOFF_SECONDS")

    # 常用模型供应商配置 ========================================================================
    # 当前只建模常用的 DeepSeek 和 SiliconFlow；其他供应商暂时交给 extra="ignore" 忽略。
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="", alias="DEEPSEEK_BASE_URL")
    siliconflow_api_key: str = Field(default="", alias="SILICONFLOW_API_KEY")
    siliconflow_base_url: str = Field(default="", alias="SILICONFLOW_BASE_URL")
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    dashscope_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", alias="DASHSCOPE_BASE_URL")
    dashscope_embedding_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1",
        alias="DASHSCOPE_EMBEDDING_BASE_URL",
    )
    qwen_model: str = Field(default="qwen3.7-plus", alias="QWEN_MODEL")

    # Schema Retrieval 配置 ===================================================================
    # 默认仍走纯本地 deterministic in-memory；Milvus / SiliconFlow 必须显式开启。
    schema_vector_backend: str = Field(default="inmemory", alias="SCHEMA_VECTOR_BACKEND")
    schema_embedding_provider: str = Field(default="deterministic", alias="SCHEMA_EMBEDDING_PROVIDER")
    milvus_collection: str = Field(default="datapilot_schema_docs", alias="MILVUS_COLLECTION")
    milvus_uri: str = Field(default="http://127.0.0.1:19530", alias="MILVUS_URI")
    milvus_reset_collection: bool = Field(default=False, alias="MILVUS_RESET_COLLECTION")
    siliconflow_embedding_model: str = Field(default="BAAI/bge-m3", alias="SILICONFLOW_EMBEDDING_MODEL")
    siliconflow_embedding_dimensions: int | None = Field(default=None, alias="SILICONFLOW_EMBEDDING_DIMENSIONS")
    qwen_embedding_model: str = Field(default="qwen3.7-text-embedding", alias="QWEN_EMBEDDING_MODEL")
    qwen_embedding_dimensions: int = Field(default=1024, alias="QWEN_EMBEDDING_DIMENSIONS")

    # EnterpriseRAG-Bench 产品 RAG ============================================================
    # ★ M44A：semantic 是产品默认，但数据快照必须显式选择。路径留空时应用仍可提供 SQL，
    # RAG readiness 则明确 unavailable；绝不能悄悄退回 lexical 或仓库内小语料。
    enterprise_rag_retrieval_mode: str = Field(default="semantic", alias="ENTERPRISE_RAG_RETRIEVAL_MODE")
    enterprise_rag_profile_root: Path | None = Field(default=None, alias="ENTERPRISE_RAG_PROFILE_ROOT")
    enterprise_rag_profile_identity: str = Field(default="", alias="ENTERPRISE_RAG_PROFILE_IDENTITY")
    enterprise_rag_semantic_root: Path | None = Field(default=None, alias="ENTERPRISE_RAG_SEMANTIC_ROOT")
    enterprise_rag_semantic_identity: str = Field(default="", alias="ENTERPRISE_RAG_SEMANTIC_IDENTITY")
    # M46-E：只允许服务端启动配置选择 acquisition strategy。默认 Pipeline 是已验证基线；
    # Subgraph 需要显式开启，HTTP 请求体没有对应字段。
    phase4b_rag_strategy: Literal["pipeline", "subgraph"] = Field(
        default="pipeline", alias="PHASE4B_RAG_STRATEGY"
    )

    # 可观测性配置 =============================================================================
    # Phase 3B 只把 LangFuse 作为“旁路观测系统”：默认关闭，不影响 JSONL 主链路。
    langfuse_enabled: bool = Field(default=False, alias="LANGFUSE_ENABLED")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    # ★ base_url 不写死 Cloud 地址，后续 EvalBench / self-host 只需换环境变量。
    langfuse_base_url: str = Field(default="https://jp.cloud.langfuse.com", alias="LANGFUSE_BASE_URL")

    # Eval Judge 配置 ==========================================================================
    # M17 才会真正使用；M15 先把配置入口钉住，空字符串表示默认不启用 L3 judge。
    eval_judge_model: str = Field(default="", alias="EVAL_JUDGE_MODEL")

    # ★ extra="ignore" 表示 `.env` 里多出来的字段先忽略，不让本地私有配置拖垮服务启动。
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """返回全局唯一的 Settings 实例（通过 lru_cache 保证单例）。

    ★ lru_cache 让 Settings 只创建一次，避免每次请求都重新读取 .env 文件。
    """
    return Settings()
