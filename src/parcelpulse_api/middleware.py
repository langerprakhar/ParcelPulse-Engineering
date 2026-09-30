"""Request-scoped context: correlation ID, access log, and last-resort error handling."""

import logging
import time

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from parcelpulse_api.correlation import (
    CORRELATION_HEADER,
    correlation_id_from_headers,
    set_correlation_id,
)
from parcelpulse_api.errors import error_body

logger = logging.getLogger("parcelpulse.request")

# Probes are polled constantly; keep them out of the INFO log.
QUIET_PATHS = frozenset({"/health", "/ready", "/metrics"})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        correlation_id = correlation_id_from_headers(headers)
        set_correlation_id(correlation_id)

        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_context(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            logger.exception("unhandled error", extra={"path": scope["path"]})
            if response_started:
                raise
            response = JSONResponse(
                status_code=500,
                content=error_body("internal_error", "Internal server error"),
            )
            await response(scope, receive, send_with_context)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            level = logging.DEBUG if scope["path"] in QUIET_PATHS else logging.INFO
            logger.log(
                level,
                "request completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
