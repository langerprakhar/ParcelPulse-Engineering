"""Dependency check for container health probes.

    python -m parcelpulse_worker.healthcheck

Exits 0 when PostgreSQL and Redis both answer, 1 otherwise. The worker has no
HTTP port, so this is what Docker runs to decide whether the container is healthy.
"""

import sys

import redis
from sqlalchemy import text

from parcelpulse_worker.config import Settings, get_settings
from parcelpulse_worker.db import create_db_engine


def check_database(settings: Settings) -> None:
    engine = create_db_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def check_redis(settings: Settings) -> None:
    if settings.queue_broker != "redis":
        return
    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.ping()
    finally:
        client.close()


def run(settings: Settings) -> dict[str, str]:
    """Returns ``{"database": "ok" | "error: ...", "redis": ...}``."""
    results: dict[str, str] = {}
    for name, check in (("database", check_database), ("redis", check_redis)):
        try:
            check(settings)
            results[name] = "ok"
        except Exception as exc:
            # Exception type only: messages can contain connection details.
            results[name] = f"error: {type(exc).__name__}"
    return results


def main() -> int:
    results = run(get_settings())
    for name, result in results.items():
        print(f"{name}: {result}")
    return 0 if all(result == "ok" for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
