from alembic.config import Config


def test_alembic_ini_is_readable_on_windows_locale() -> None:
    # Windows 默认 locale 可能是 GBK；alembic.ini 必须保持可读，避免迁移命令
    # 在读取配置阶段就失败。这个测试专门防止非 ASCII 注释再次引发编码问题。
    config = Config("alembic.ini")

    assert config.get_main_option("script_location") == "alembic"
