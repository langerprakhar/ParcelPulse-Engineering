"""Runtime configuration, loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "parcelpulse-worker"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # The database owned by parcelpulse-api. The worker only touches `notifications`
    # (read/write) and reads `shipments` and `tracking_events`.
    database_url: str

    # Queue contract with parcelpulse-api; see docs/notification-system.md.
    redis_url: str = "redis://localhost:6379/0"
    queue_broker: Literal["redis", "stub"] = "redis"
    notification_queue_name: str = "notifications"
    notification_actor_name: str = "deliver_notification"

    # Email delivery. "log" writes the message to the log instead of sending it.
    email_provider: Literal["smtp", "log"] = "smtp"
    email_from: str = "ParcelPulse <notifications@parcelpulse.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_timeout_seconds: float = 10.0

    # Used to build the "track your parcel" link in messages.
    web_base_url: str = "http://localhost:3000"

    # Retry policy: attempt n+1 happens base * 2^(n-1) seconds after attempt n fails.
    notification_max_attempts: int = Field(default=5, ge=1)
    notification_retry_base_seconds: float = Field(default=30.0, gt=0)
    notification_retry_max_seconds: float = Field(default=3600.0, gt=0)

    # A notification left in SENDING longer than this is assumed abandoned.
    sending_lease_seconds: float = Field(default=120.0, gt=0)

    # Sweeper: recovers notifications whose queue message was lost.
    sweep_interval_seconds: float = Field(default=15.0, gt=0)
    sweep_grace_seconds: float = Field(default=30.0, ge=0)
    sweep_batch_size: int = Field(default=100, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
