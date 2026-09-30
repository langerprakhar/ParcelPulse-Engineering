"""Runtime configuration, loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "INFO"

    # The carrier code sent as "provider" in every webhook.
    carrier_code: str = "simcarrier"

    # Where tracking events are delivered, and the secret shared with the receiver.
    webhook_url: str = "http://localhost:8000/webhooks/carrier"
    webhook_signing_secret: SecretStr

    # Like a real carrier, a failed delivery is retried with a growing delay.
    webhook_max_attempts: int = Field(default=4, ge=1)
    webhook_retry_backoff_seconds: float = Field(default=0.5, ge=0)
    webhook_timeout_seconds: float = Field(default=5.0, gt=0)

    # Only used when a caller asks the simulator to also register the shipment
    # in ParcelPulse (a convenience for demos, smoke tests and load tests).
    parcelpulse_api_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
