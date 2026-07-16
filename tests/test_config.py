from app.core.config import Settings


def test_settings_default_database_url_targets_mysql() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("mysql+pymysql://")


def test_settings_ignore_unrelated_env_keys(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=test",
                "DATABASE_URL=sqlite:///./.codex/temp_work/test.db",
                "UNRELATED_VENDOR_SETTING=keep-out-of-settings",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///./.codex/temp_work/test.db"


def test_settings_load_provider_specific_llm_keys(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=deepseek-key",
                "DEEPSEEK_BASE_URL=https://api.deepseek.example/v1",
                "SILICONFLOW_API_KEY=siliconflow-key",
                "SILICONFLOW_BASE_URL=https://siliconflow.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.deepseek_api_key == "deepseek-key"
    assert settings.deepseek_base_url == "https://api.deepseek.example/v1"
    assert settings.siliconflow_api_key == "siliconflow-key"
    assert settings.siliconflow_base_url == "https://siliconflow.example/v1"
