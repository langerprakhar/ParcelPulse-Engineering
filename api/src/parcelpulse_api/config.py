"""Runtime configuration, loaded from environment variables."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_SIGNING_SECRET_LENGTH = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    service_name: str = "parcelpulse-api"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:password@host:5432/parcelpulse
    database_url: str

    # Comma-separated carrier codes that shipments may be registered for.
    supported_carriers: Annotated[list[str], NoDecode] = ["simcarrier"]

    # Notification hand-off to parcelpulse-worker (see parcelpulse_api.queue).
    redis_url: str = "redis://localhost:6379/0"
    notification_queue_name: str = "notifications"
    notification_actor_name: str = "deliver_notification"

    # Carrier webhook authentication (see parcelpulse_api.security).
    webhook_signature_required: bool = True
    webhook_signing_secret: SecretStr | None = None
    webhook_signature_tolerance_seconds: int = 300
    webhook_max_body_bytes: int = 65536
    # Reject events dated further in the future than this; a wrong carrier clock
    # must not be able to pin a shipment's status.
    webhook_max_future_skew_seconds: int = 3600

    # Development/debug endpoints under /dev. Never available in production.
    enable_dev_endpoints: bool = False

    @field_validator("supported_carriers", mode="before")
    @classmethod
    def _split_carriers(cls, value: object) -> object:
        if isinstance(value, str):
            return [code.strip().lower() for code in value.split(",") if code.strip()]
        return value

    @model_validator(mode="after")
    def _validate_webhook_signing(self) -> Self:
        if not self.webhook_signature_required:
            return self
        secret = self.webhook_signing_secret
        if secret is None or len(secret.get_secret_value()) < MIN_SIGNING_SECRET_LENGTH:
            raise ValueError(
                "WEBHOOK_SIGNING_SECRET must be set to at least "
                f"{MIN_SIGNING_SECRET_LENGTH} characters unless WEBHOOK_SIGNATURE_REQUIRED=false"
            )
        return self

    @model_validator(mode="after")
    def _enforce_production_rules(self) -> Self:
        if self.environment != "production":
            return self
        if self.enable_dev_endpoints:
            raise ValueError("ENABLE_DEV_ENDPOINTS must not be set when ENVIRONMENT=production")
        if not self.webhook_signature_required:
            raise ValueError("WEBHOOK_SIGNATURE_REQUIRED must be true when ENVIRONMENT=production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
