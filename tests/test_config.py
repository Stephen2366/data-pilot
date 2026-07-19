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
    """验证各 LLM 供应商（DeepSeek / SiliconFlow）的 API Key 和 Base URL 能正确加载。"""
    settings = Settings(
        DEEPSEEK_API_KEY="deepseek-key",
        DEEPSEEK_BASE_URL="https://api.deepseek.example/v1",
        SILICONFLOW_API_KEY="siliconflow-key",
        SILICONFLOW_BASE_URL="https://siliconflow.example/v1",
    )

    assert settings.deepseek_api_key == "deepseek-key"
    assert settings.deepseek_base_url == "https://api.deepseek.example/v1"
    assert settings.siliconflow_api_key == "siliconflow-key"
    assert settings.siliconflow_base_url == "https://siliconflow.example/v1"
