"""Fixtures for tests that need a real PostgreSQL database.

The schema is built from zero with Alembic once per test session, so every
integration run also exercises the migrations. Tables are emptied before each
test. Start a disposable database with::

    docker compose -f docker-compose.dev.yml up -d --wait
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from parcelpulse_api.config import Settings
from parcelpulse_api.models import Base
from tests.conftest import make_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://parcelpulse:parcelpulse@localhost:55432/parcelpulse_test"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in Path(str(item.fspath)).parts:
            item.add_marker(pytest.mark.integration)


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(
            f"Refusing to run integration tests against database '{database}': "
            "the name must end with '_test' because the schema is dropped and rebuilt.",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    except OperationalError as exc:
        pytest.fail(
            "Integration tests need PostgreSQL. Start one with "
            "'docker compose -f docker-compose.dev.yml up -d --wait' or set TEST_DATABASE_URL. "
            f"Connection error: {exc.orig}",
            pytrace=False,
        )
    command.upgrade(alembic_config(database_url), "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(migrated_engine: Engine) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with migrated_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def settings(database_url: str) -> Settings:
    return make_settings(database_url=database_url)


@pytest.fixture
def session_factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session for arranging data and asserting on what the API committed."""
    with session_factory() as session:
        yield session
