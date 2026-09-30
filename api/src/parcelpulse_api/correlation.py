"""Correlation IDs: one identifier per inbound request, carried through logs and responses."""

import re
import uuid
from contextvars import ContextVar

CORRELATION_HEADER = "X-Correlation-ID"
_ACCEPTED_HEADERS = ("x-correlation-id", "x-request-id")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def correlation_id_from_headers(headers: dict[str, str]) -> str:
    """Reuse a caller-supplied ID when it is safe to log, otherwise mint a new one."""
    for name in _ACCEPTED_HEADERS:
        candidate = headers.get(name)
        if candidate and _SAFE_ID.match(candidate):
            return candidate
    return new_correlation_id()
