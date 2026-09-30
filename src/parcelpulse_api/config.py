"""Runtime configuration, loaded from environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    service_name: str = "parcelpulse-api"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Development/debug endpoints under /dev. Never available in production.
    enable_dev_endpoints: bool = False

    @model_validator(mode="after")
    def _enforce_production_rules(self) -> Self:
        if self.environment == "production" and self.enable_dev_endpoints:
            raise ValueError("ENABLE_DEV_ENDPOINTS must not be set when ENVIRONMENT=production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
