"""配置模块单元测试。

★ 验证 Settings 能从环境变量/.env 正确加载各类配置项，
以及不相关字段被正确忽略（extra="ignore"）。
"""

from app.core.config import Settings


def test_settings_default_database_url_targets_mysql() -> None:
    """验证默认数据库 URL 指向 MySQL：项目开发库统一使用 MySQL，确保没被误改成 SQLite。"""
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("mysql+pymysql://")


def test_settings_ignore_unrelated_env_keys() -> None:
    """验证 extra="ignore"：env 文件中多出来的字段不导致 Settings 初始化失败。"""
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="sqlite:///./.agent_work/temp/test.db",
        UNRELATED_VENDOR_SETTING="keep-out-of-settings",
    )

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///./.agent_work/temp/test.db"


def test_settings_load_provider_specific_llm_keys() -> None:
    """验证各 LLM 供应商（DeepSeek / SiliconFlow / Qwen）的 API Key 和 Base URL 能正确加载。"""
    settings = Settings(
        DEEPSEEK_API_KEY="deepseek-key",
        DEEPSEEK_BASE_URL="https://api.deepseek.example/v1",
        SILICONFLOW_API_KEY="siliconflow-key",
        SILICONFLOW_BASE_URL="https://siliconflow.example/v1",
        DASHSCOPE_API_KEY="dashscope-key",
        DASHSCOPE_BASE_URL="https://dashscope.example/compatible-mode/v1",
        QWEN_MODEL="qwen3.7-plus",
        QWEN_EMBEDDING_MODEL="qwen3.7-text-embedding",
        QWEN_EMBEDDING_DIMENSIONS="1024",
    )

    assert settings.deepseek_api_key == "deepseek-key"
    assert settings.deepseek_base_url == "https://api.deepseek.example/v1"
    assert settings.siliconflow_api_key == "siliconflow-key"
    assert settings.siliconflow_base_url == "https://siliconflow.example/v1"
    assert settings.dashscope_api_key == "dashscope-key"
    assert settings.dashscope_base_url == "https://dashscope.example/compatible-mode/v1"
    assert settings.qwen_model == "qwen3.7-plus"
    assert settings.qwen_embedding_model == "qwen3.7-text-embedding"
    assert settings.qwen_embedding_dimensions == 1024


def test_settings_load_langfuse_and_judge_config() -> None:
    """验证 Phase 3B LangFuse / L3 judge 配置能读取，且默认关闭不影响原链路。"""
    default_settings = Settings(_env_file=None)

    assert default_settings.langfuse_enabled is False
    assert default_settings.eval_judge_model == ""

    settings = Settings(
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
        LANGFUSE_BASE_URL="http://localhost:3000",
        EVAL_JUDGE_MODEL="deepseek-v3-judge",
    )

    assert settings.langfuse_enabled is True
    assert settings.langfuse_public_key == "pk-test"
    assert settings.langfuse_secret_key == "sk-test"
    assert settings.langfuse_base_url == "http://localhost:3000"
    assert settings.eval_judge_model == "deepseek-v3-judge"


def test_thread_checkpoint_ttl_is_finite_and_configurable() -> None:
    """M36 进程内 pending 状态不能无限存活，且部署时可缩短 TTL。"""

    assert Settings(_env_file=None).thread_checkpoint_ttl_seconds == 900
    assert Settings(_env_file=None, THREAD_CHECKPOINT_TTL_SECONDS="30").thread_checkpoint_ttl_seconds == 30


def test_enterprise_rag_defaults_semantic_but_requires_explicit_snapshot_paths() -> None:
    """M44A 不把空配置解释成 lexical，也不在代码中猜本机 dataset 路径。"""

    settings = Settings(_env_file=None)
    assert settings.enterprise_rag_retrieval_mode == "semantic"
    assert settings.enterprise_rag_profile_root is None
    assert settings.enterprise_rag_profile_identity == ""
    assert settings.enterprise_rag_semantic_root is None
    assert settings.enterprise_rag_semantic_identity == ""
