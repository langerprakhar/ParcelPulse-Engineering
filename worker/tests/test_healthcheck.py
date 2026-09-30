from parcelpulse_worker import healthcheck
from tests.conftest import make_settings


def test_healthy_when_the_database_answers(database_url: str) -> None:
    # The stub broker needs no Redis, so only the database is dialled.
    settings = make_settings(database_url=database_url, queue_broker="stub")
    assert healthcheck.run(settings) == {"database": "ok", "redis": "ok"}


def test_unreachable_database_is_reported_without_connection_details() -> None:
    settings = make_settings(
        database_url="postgresql+psycopg://app:s3cret-password@localhost:1/db?connect_timeout=1"
    )

    results = healthcheck.run(settings)

    assert results["database"] == "error: OperationalError"
    assert "s3cret-password" not in str(results)


def test_unreachable_redis_is_reported(database_url: str) -> None:
    settings = make_settings(
        database_url=database_url, queue_broker="redis", redis_url="redis://localhost:1/0"
    )

    results = healthcheck.run(settings)

    assert results["database"] == "ok"
    assert results["redis"].startswith("error: ")
