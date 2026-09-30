"""Application factory.

Run with ``uvicorn parcelpulse_api.main:create_app --factory``.
"""

from fastapi import FastAPI

from parcelpulse_api import __version__
from parcelpulse_api.config import Settings, get_settings
from parcelpulse_api.errors import install_error_handlers
from parcelpulse_api.logging_config import configure_logging
from parcelpulse_api.middleware import RequestContextMiddleware
from parcelpulse_api.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(
        service=settings.service_name,
        level=settings.log_level,
        log_format=settings.log_format,
    )

    app = FastAPI(
        title="ParcelPulse API",
        version=__version__,
        description="Shipment tracking, carrier webhook ingestion and delivery notifications.",
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    return app
