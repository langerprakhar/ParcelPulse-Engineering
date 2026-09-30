"""Liveness, readiness and metrics endpoints."""

import logging
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

from parcelpulse_api import __version__
from parcelpulse_api.metrics import CONTENT_TYPE

logger = logging.getLogger("parcelpulse.health")

router = APIRouter(tags=["operations"])

CheckResult = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResult]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(request: Request) -> HealthResponse:
    """Reports that the process is up. Does not touch any dependency."""
    return HealthResponse(
        status="ok",
        service=request.app.state.settings.service_name,
        version=__version__,
    )


def _check_database(request: Request) -> None:
    with request.app.state.engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def _check_redis(request: Request) -> None:
    request.app.state.notification_publisher.ping()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
)
def ready(request: Request, response: Response) -> ReadinessResponse:
    """Checks the dependencies needed to serve traffic: PostgreSQL and Redis."""
    checks: dict[str, CheckResult] = {}
    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            check(request)
            checks[name] = "ok"
        except Exception:
            # Details go to the log only; the response must not leak connection strings.
            logger.warning("readiness check failed", extra={"check": name}, exc_info=True)
            checks[name] = "error"

    is_ready = all(result == "ok" for result in checks.values())
    if not is_ready:
        response.status_code = 503
    return ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    return Response(content=request.app.state.metrics.render(), media_type=CONTENT_TYPE)
