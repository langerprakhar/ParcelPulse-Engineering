from fastapi.testclient import TestClient

from parcelpulse_api.main import create_app
from parcelpulse_api.queue import InMemoryNotificationPublisher
from tests.conftest import make_settings


def test_not_ready_when_the_database_is_unreachable_and_credentials_do_not_leak() -> None:
    settings = make_settings(
        database_url="postgresql+psycopg://app:s3cret-db-password@localhost:1/parcelpulse"
        "?connect_timeout=1"
    )
    app = create_app(settings, notification_publisher=InMemoryNotificationPublisher())

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "error", "redis": "ok"},
    }
    assert "s3cret-db-password" not in response.text


def test_production_configuration_cannot_expose_dev_endpoints() -> None:
    settings = make_settings(environment="production")
    app = create_app(settings, notification_publisher=InMemoryNotificationPublisher())

    with TestClient(app) as client:
        assert client.get("/dev/webhook-receipts").status_code == 404
