"""Liveness endpoint."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from parcelpulse_api import __version__

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(request: Request) -> HealthResponse:
    """Reports that the process is up. Does not touch any dependency."""
    return HealthResponse(
        status="ok",
        service=request.app.state.settings.service_name,
        version=__version__,
    )
