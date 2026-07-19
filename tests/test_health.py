"""健康检查与工具函数单元测试。"""

from fastapi.testclient import TestClient

from app.main import app, redact_database_url


def test_health_returns_ok_status() -> None:
    """验证 /health 接口返回 200 和 {"status": "ok"}——服务存活的底线保障。"""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_redact_database_url_hides_password() -> None:
    """验证数据库连接串脱敏：密码部分被替换为 ***，且原始密码不出现在结果中。"""
    redacted = redact_database_url(
        "mysql+pymysql://datapilot_user:change-me@127.0.0.1:3306/datapilot_dev"
    )

    assert redacted == "mysql+pymysql://datapilot_user:***@127.0.0.1:3306/datapilot_dev"
    assert "change-me" not in redacted
