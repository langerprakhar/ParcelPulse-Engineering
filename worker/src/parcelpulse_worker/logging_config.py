"""Structured logging.

Every record is one JSON object carrying the correlation ID of the webhook
delivery that caused the work. Values logged through ``extra=`` under a
sensitive-looking key are redacted.
"""

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}
_SENSITIVE_MARKERS = ("secret", "token", "password", "authorization", "api_key")
REDACTED = "[redacted]"

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


@contextmanager
def correlation_scope(correlation_id: str | None) -> Iterator[None]:
    """Attach a correlation ID to every log record emitted inside the block."""
    token = _correlation_id.set(correlation_id)
    try:
        yield
    finally:
        _correlation_id.reset(token)


def _redact(key: str, value: Any) -> Any:
    if any(marker in key.lower() for marker in _SENSITIVE_MARKERS):
        return REDACTED
    return value


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: _redact(key, value)
        for key, value in record.__dict__.items()
        if key not in _RESERVED and not key.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self._service,
            "correlation_id": get_correlation_id(),
            **_extras(record),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        correlation_id = get_correlation_id()
        if correlation_id:
            line += f" correlation_id={correlation_id}"
        extras = " ".join(f"{key}={value}" for key, value in _extras(record).items())
        if extras:
            line += f" {extras}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(*, service: str, level: str = "INFO", log_format: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service) if log_format == "json" else ConsoleFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
