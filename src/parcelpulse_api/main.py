"""Application factory.

Run with ``uvicorn parcelpulse_api.main:create_app --factory``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from parcelpulse_api import __version__
from parcelpulse_api.config import Settings, get_settings
from parcelpulse_api.db import create_db_engine, create_session_factory
from parcelpulse_api.errors import install_error_handlers
from parcelpulse_api.logging_config import configure_logging
from parcelpulse_api.middleware import RequestContextMiddleware
from parcelpulse_api.routers import health, shipments


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.engine.dispose()


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
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)

    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(shipments.router)
    return app
