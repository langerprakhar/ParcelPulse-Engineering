from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from parcelpulse_api.config import Settings
from parcelpulse_api.main import create_app


def make_settings(**overrides: object) -> Settings:
    """Settings for tests: never reads a developer's local .env file."""
    values: dict[str, object] = {"environment": "test", "log_format": "console"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
