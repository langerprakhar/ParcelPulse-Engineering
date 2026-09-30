"""Structured logging.

Every record is emitted as one JSON object carrying the current correlation ID.
Values logged through ``extra=`` under a sensitive-looking key are redacted.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from parcelpulse_api.correlation import get_correlation_id

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "color_message",  # uvicorn's ANSI-coloured duplicate of the message
}
_SENSITIVE_MARKERS = ("secret", "token", "password", "authorization", "signature", "api_key")
REDACTED = "[redacted]"


def _redact(key: str, value: Any) -> Any:
    if any(marker in key.lower() for marker in _SENSITIVE_MARKERS):
        return REDACTED
    return value


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
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = _redact(key, value)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = " ".join(
            f"{key}={_redact(key, value)}"
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        )
        line = f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        correlation_id = get_correlation_id()
        if correlation_id:
            line += f" correlation_id={correlation_id}"
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
    # Route uvicorn's own messages through the same formatter.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # Request logging is done by RequestContextMiddleware; avoid duplicate access lines.
    logging.getLogger("uvicorn.access").disabled = True
