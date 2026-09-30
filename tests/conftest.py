from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from parcelpulse_api.config import Settings
from parcelpulse_api.main import create_app
from parcelpulse_api.queue import InMemoryNotificationPublisher
from tests.helpers import TEST_SIGNING_SECRET

# Engines connect lazily, so unit tests can use a URL that is never dialled.
UNUSED_DATABASE_URL = "postgresql+psycopg://unused:unused@localhost:1/unused"


def make_settings(**overrides: object) -> Settings:
    """Settings for tests: never reads a developer's local .env file."""
    values: dict[str, object] = {
        "environment": "test",
        "log_format": "console",
        "database_url": UNUSED_DATABASE_URL,
        "webhook_signing_secret": TEST_SIGNING_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def publisher() -> InMemoryNotificationPublisher:
    return InMemoryNotificationPublisher()


@pytest.fixture
def app(settings: Settings, publisher: InMemoryNotificationPublisher) -> FastAPI:
    return create_app(settings, notification_publisher=publisher)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
