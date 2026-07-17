from alembic.config import Config


def test_alembic_ini_is_readable_on_windows_locale() -> None:
    config = Config("alembic.ini")

    assert config.get_main_option("script_location") == "alembic"
