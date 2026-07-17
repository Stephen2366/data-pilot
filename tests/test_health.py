from fastapi.testclient import TestClient

from app.main import app, redact_database_url


def test_health_returns_ok_status() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_redact_database_url_hides_password() -> None:
    redacted = redact_database_url(
        "mysql+pymysql://datapilot_user:change-me@127.0.0.1:3306/datapilot_dev"
    )

    assert redacted == "mysql+pymysql://datapilot_user:***@127.0.0.1:3306/datapilot_dev"
    assert "change-me" not in redacted
