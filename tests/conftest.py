"""Shared fixtures.

Tests that touch the database run against a real PostgreSQL. The schema is
created from the worker's own table mirror (see parcelpulse_worker.db); the
real schema is owned by parcelpulse-api and the two are checked against each
other by the full-stack smoke test in parcelpulse-infra.

    docker compose -f docker-compose.dev.yml up -d --wait
"""

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import dramatiq
import pytest

# The actors module builds its broker from the environment when it is imported.
# Force the in-memory broker before anything imports it, so tests can never talk
# to a real Redis.
os.environ["QUEUE_BROKER"] = "stub"
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost:1/unused")
os.environ.setdefault("LOG_FORMAT", "console")

from sqlalchemy import Engine, create_engine, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from parcelpulse_worker import actors, runtime
from parcelpulse_worker.config import Settings
from parcelpulse_worker.db import metadata, notifications, shipments, tracking_events
from parcelpulse_worker.senders import InMemoryEmailSender

# Engines connect lazily, so tests that never query can use a URL that is never dialled.
UNUSED_DATABASE_URL = "postgresql+psycopg://unused:unused@localhost:1/unused"
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://parcelpulse:parcelpulse@localhost:55433/parcelpulse_worker_test"
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def make_settings(**overrides: object) -> Settings:
    """Settings for tests: never reads a developer's local .env file."""
    values: dict[str, object] = {
        "log_format": "console",
        "database_url": UNUSED_DATABASE_URL,
        "queue_broker": "stub",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(
            f"Refusing to run tests against database '{database}': "
            "the name must end with '_test' because its tables are dropped and recreated.",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="session")
def schema_engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    try:
        metadata.drop_all(engine)
    except OperationalError as exc:
        pytest.fail(
            "These tests need PostgreSQL. Start one with "
            "'docker compose -f docker-compose.dev.yml up -d --wait' or set TEST_DATABASE_URL. "
            f"Connection error: {exc.orig}",
            pytrace=False,
        )
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def engine(schema_engine: Engine) -> Engine:
    tables = ", ".join(f'"{table.name}"' for table in metadata.sorted_tables)
    with schema_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    return schema_engine


@pytest.fixture
def settings(database_url: str) -> Settings:
    return make_settings(database_url=database_url)


@pytest.fixture
def sender() -> InMemoryEmailSender:
    return InMemoryEmailSender()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def create_notification(
    engine: Engine,
    *,
    notification_type: str = "OUT_FOR_DELIVERY",
    status: str = "PENDING",
    destination: str = "recipient@example.com",
    channel: str = "EMAIL",
    attempts: int = 0,
    created_at: datetime = NOW,
    **columns: Any,
) -> uuid.UUID:
    """Insert a shipment, a tracking event and a notification for it, as the API would."""
    shipment_id, event_id, notification_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(shipments).values(
                id=shipment_id,
                tracking_number=f"SC{shipment_id.hex[:10].upper()}",
                carrier="simcarrier",
                current_status=notification_type,
                estimated_delivery_at=NOW + timedelta(hours=6),
            )
        )
        connection.execute(
            insert(tracking_events).values(
                id=event_id,
                shipment_id=shipment_id,
                event_type=notification_type,
                event_at=NOW - timedelta(minutes=5),
                location={"facility": "Leeds Hub", "city": "Leeds", "country": "GB"},
                description="Loaded on delivery vehicle",
            )
        )
        connection.execute(
            insert(notifications).values(
                id=notification_id,
                shipment_id=shipment_id,
                tracking_event_id=event_id,
                type=notification_type,
                channel=channel,
                destination=destination,
                status=status,
                attempts=attempts,
                created_at=created_at,
                updated_at=created_at,
                **columns,
            )
        )
    return notification_id


def get_notification(engine: Engine, notification_id: uuid.UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            select(notifications).where(notifications.c.id == notification_id)
        ).one()


QUEUE = "notifications"


class Harness:
    """A real Dramatiq worker on the in-memory broker."""

    def __init__(self, worker: dramatiq.Worker) -> None:
        self.worker = worker

    def drain(self) -> None:
        """Block until every message, including delayed retries, has been processed."""
        actors.broker.join(QUEUE, timeout=20_000, fail_fast=False)
        self.worker.join()


@pytest.fixture
def harness(engine: Engine, sender: InMemoryEmailSender, database_url: str) -> Iterator[Harness]:
    harness_settings = make_settings(
        database_url=database_url,
        notification_max_attempts=3,
        # Keep retry delays short enough to run for real.
        notification_retry_base_seconds=0.05,
    )
    runtime.set_runtime(runtime.Runtime(settings=harness_settings, engine=engine, sender=sender))
    actors.broker.flush_all()
    worker = dramatiq.Worker(actors.broker, worker_timeout=50, worker_threads=4)
    worker.start()
    yield Harness(worker)
    worker.stop()
    actors.broker.flush_all()
    runtime.set_runtime(None)
