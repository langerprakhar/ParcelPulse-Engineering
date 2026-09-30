from parcelpulse_worker.config import Settings

# Engines connect lazily, so tests that never query can use a URL that is never dialled.
UNUSED_DATABASE_URL = "postgresql+psycopg://unused:unused@localhost:1/unused"


def make_settings(**overrides: object) -> Settings:
    """Settings for tests: never reads a developer's local .env file."""
    values: dict[str, object] = {
        "log_format": "console",
        "database_url": UNUSED_DATABASE_URL,
        "queue_broker": "stub",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]
