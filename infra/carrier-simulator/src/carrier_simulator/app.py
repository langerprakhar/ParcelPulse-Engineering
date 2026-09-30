"""HTTP API of the carrier simulator.

Run with ``uvicorn carrier_simulator.app:create_app --factory --port 8100``.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

import httpx2
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from carrier_simulator import __version__
from carrier_simulator.config import Settings, get_settings
from carrier_simulator.scenarios import DEFAULT_SCENARIO, SCENARIOS
from carrier_simulator.sender import WebhookSender
from carrier_simulator.simulator import (
    Delivery,
    RegistrationError,
    SimulatedShipment,
    Simulator,
    SimulatorError,
    UnknownShipmentError,
)

logger = logging.getLogger("carrier_simulator")


# --- Request and response models ---------------------------------------------


class CreateShipmentRequest(BaseModel):
    scenario: str = DEFAULT_SCENARIO
    tracking_number: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{6,40}$")
    # Sent as "register"; the attribute name avoids shadowing BaseModel.register.
    register_shipment: bool = Field(
        default=False,
        alias="register",
        description="Also register the shipment in ParcelPulse (POST /shipments).",
    )
    notification_email: str | None = Field(
        default=None, description="Passed to ParcelPulse when registering."
    )


class CountRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50)


class DuplicateRequest(BaseModel):
    event_id: str | None = Field(default=None, description="Defaults to the last event sent.")
    count: int = Field(default=1, ge=1, le=50)


class LifecycleRequest(BaseModel):
    shuffle: bool = False
    duplicates: int = Field(default=0, ge=0, le=10, description="Extra sends of each event.")


class BurstRequest(BaseModel):
    shipments: int = Field(default=10, ge=1, le=500)
    scenario: str = DEFAULT_SCENARIO
    register_shipment: bool = Field(default=True, alias="register")
    shuffle: bool = False
    duplicates: int = Field(default=0, ge=0, le=10)
    concurrency: int = Field(default=8, ge=1, le=64)


class AttemptOut(BaseModel):
    number: int
    status_code: int | None
    duration_ms: float
    error: str | None
    result: str | None


class DeliveryOut(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    duplicate: bool
    delivered: bool
    result: str | None
    attempts: list[AttemptOut]


class EventOut(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    state: str
    description: str


class ShipmentOut(BaseModel):
    tracking_number: str
    scenario: str
    registered: bool
    started_at: datetime
    events: list[EventOut]
    deliveries: list[DeliveryOut]


class ShipmentSummary(BaseModel):
    tracking_number: str
    scenario: str
    registered: bool
    planned: int
    held: int
    sent: int


class OperationResult(BaseModel):
    tracking_number: str
    deliveries: list[DeliveryOut]


class HeldResult(BaseModel):
    tracking_number: str
    held: list[EventOut]


class BurstResult(BaseModel):
    shipments: int
    events: int
    deliveries: int
    http_attempts: int
    undelivered: int
    results: dict[str, int]
    duration_seconds: float
    tracking_numbers: list[str]


def _delivery_out(delivery: Delivery) -> DeliveryOut:
    return DeliveryOut(
        event_id=delivery.event_id,
        event_type=delivery.event_type,
        occurred_at=delivery.occurred_at,
        duplicate=delivery.duplicate,
        delivered=delivery.send.delivered,
        result=delivery.send.result,
        attempts=[
            AttemptOut(
                number=attempt.number,
                status_code=attempt.status_code,
                duration_ms=attempt.duration_ms,
                error=attempt.error,
                result=attempt.result,
            )
            for attempt in delivery.send.attempts
        ],
    )


def _events_out(shipment: SimulatedShipment) -> list[EventOut]:
    return [
        EventOut(
            event_id=event.event_id,
            event_type=event.step.event_type,
            occurred_at=event.occurred_at,
            state=event.state,
            description=event.step.description,
        )
        for event in shipment.events
    ]


def _shipment_out(shipment: SimulatedShipment) -> ShipmentOut:
    return ShipmentOut(
        tracking_number=shipment.tracking_number,
        scenario=shipment.scenario,
        registered=shipment.registered,
        started_at=shipment.started_at,
        events=_events_out(shipment),
        deliveries=[_delivery_out(delivery) for delivery in shipment.deliveries],
    )


def _operation(tracking_number: str, deliveries: list[Delivery]) -> OperationResult:
    return OperationResult(
        tracking_number=tracking_number.strip().upper(),
        deliveries=[_delivery_out(delivery) for delivery in deliveries],
    )


# --- Application --------------------------------------------------------------


def build_simulator(settings: Settings, client: httpx2.Client) -> Simulator:
    sender = WebhookSender(
        client,
        url=settings.webhook_url,
        secret=settings.webhook_signing_secret.get_secret_value(),
        max_attempts=settings.webhook_max_attempts,
        backoff_seconds=settings.webhook_retry_backoff_seconds,
    )

    def register(tracking_number: str, notification_email: str | None) -> None:
        body: dict[str, Any] = {
            "tracking_number": tracking_number,
            "carrier": settings.carrier_code,
        }
        if notification_email:
            body["notification_email"] = notification_email
        url = f"{settings.parcelpulse_api_url.rstrip('/')}/shipments"
        try:
            response = client.post(url, json=body)
        except httpx2.HTTPError as exc:
            raise RegistrationError(
                f"could not reach ParcelPulse to register the shipment: {type(exc).__name__}"
            ) from exc
        # 409 means it is already registered, which is what we wanted.
        if response.status_code not in (201, 409):
            raise RegistrationError(
                f"ParcelPulse refused the registration (HTTP {response.status_code})"
            )

    return Simulator(sender, carrier_code=settings.carrier_code, register=register)


def get_simulator(request: Request) -> Simulator:
    simulator: Simulator = request.app.state.simulator
    return simulator


SimulatorDep = Annotated[Simulator, Depends(get_simulator)]


def create_app(settings: Settings | None = None, client: httpx2.Client | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    http_client = client or httpx2.Client(timeout=settings.webhook_timeout_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        http_client.close()

    app = FastAPI(
        title="ParcelPulse carrier simulator",
        version=__version__,
        description=(
            "A stand-in for a parcel carrier. It sends signed tracking webhooks to "
            "ParcelPulse, including duplicates, delayed and out-of-order events."
        ),
        lifespan=lifespan,
    )
    app.state.simulator = build_simulator(settings, http_client)

    @app.exception_handler(UnknownShipmentError)
    async def _unknown(_: Request, exc: UnknownShipmentError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    @app.exception_handler(RegistrationError)
    async def _registration(_: Request, exc: RegistrationError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"error": str(exc)})

    @app.exception_handler(SimulatorError)
    async def _conflict(_: Request, exc: SimulatorError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "carrier-simulator", "version": __version__}

    @app.get("/scenarios")
    def scenarios() -> dict[str, list[dict[str, Any]]]:
        return {
            name: [
                {
                    "event_type": step.event_type,
                    "offset_hours": step.offset_hours,
                    "description": step.description,
                }
                for step in steps
            ]
            for name, steps in SCENARIOS.items()
        }

    @app.post("/shipments", response_model=ShipmentOut, status_code=201)
    def create_shipment(body: CreateShipmentRequest, simulator: SimulatorDep) -> ShipmentOut:
        """Create a simulated shipment with a planned journey. Sends nothing yet."""
        shipment = simulator.create_shipment(
            scenario=body.scenario,
            tracking_number=body.tracking_number,
            register=body.register_shipment,
            notification_email=body.notification_email,
        )
        return _shipment_out(shipment)

    @app.get("/shipments", response_model=list[ShipmentSummary])
    def list_shipments(simulator: SimulatorDep) -> list[ShipmentSummary]:
        return [
            ShipmentSummary(
                tracking_number=shipment.tracking_number,
                scenario=shipment.scenario,
                registered=shipment.registered,
                planned=len(shipment.in_state("planned")),
                held=len(shipment.in_state("held")),
                sent=len(shipment.in_state("sent")),
            )
            for shipment in simulator.all_shipments()
        ]

    @app.delete("/shipments")
    def reset(simulator: SimulatorDep) -> dict[str, int]:
        """Forget every simulated shipment."""
        return {"removed": simulator.reset()}

    @app.get("/shipments/{tracking_number}", response_model=ShipmentOut)
    def get_shipment(tracking_number: str, simulator: SimulatorDep) -> ShipmentOut:
        return _shipment_out(simulator.get(tracking_number))

    @app.post("/shipments/{tracking_number}/advance", response_model=OperationResult)
    def advance(
        tracking_number: str, simulator: SimulatorDep, body: CountRequest | None = None
    ) -> OperationResult:
        """Send the next planned event(s) in journey order."""
        count = body.count if body else 1
        return _operation(tracking_number, simulator.advance(tracking_number, count=count))

    @app.post("/shipments/{tracking_number}/hold", response_model=HeldResult)
    def hold(
        tracking_number: str, simulator: SimulatorDep, body: CountRequest | None = None
    ) -> HeldResult:
        """Withhold the next planned event(s); `release-held` sends them late."""
        held = simulator.hold(tracking_number, count=body.count if body else 1)
        return HeldResult(
            tracking_number=tracking_number.strip().upper(),
            held=[
                EventOut(
                    event_id=event.event_id,
                    event_type=event.step.event_type,
                    occurred_at=event.occurred_at,
                    state=event.state,
                    description=event.step.description,
                )
                for event in held
            ],
        )

    @app.post("/shipments/{tracking_number}/release-held", response_model=OperationResult)
    def release_held(tracking_number: str, simulator: SimulatorDep) -> OperationResult:
        """Send held events now: a delayed delivery of something that happened earlier."""
        return _operation(tracking_number, simulator.release_held(tracking_number))

    @app.post("/shipments/{tracking_number}/out-of-order", response_model=OperationResult)
    def out_of_order(tracking_number: str, simulator: SimulatorDep) -> OperationResult:
        """Send the next two planned events in swapped order."""
        return _operation(tracking_number, simulator.out_of_order(tracking_number))

    @app.post("/shipments/{tracking_number}/duplicate", response_model=OperationResult)
    def duplicate(
        tracking_number: str, simulator: SimulatorDep, body: DuplicateRequest | None = None
    ) -> OperationResult:
        """Redeliver an already sent event, byte for byte, with a fresh signature."""
        body = body or DuplicateRequest()
        deliveries = simulator.duplicate(tracking_number, event_id=body.event_id, count=body.count)
        return _operation(tracking_number, deliveries)

    @app.post("/shipments/{tracking_number}/exception", response_model=OperationResult)
    def exception(tracking_number: str, simulator: SimulatorDep) -> OperationResult:
        """Inject a delivery exception after the most recently sent event."""
        return _operation(tracking_number, simulator.exception(tracking_number))

    @app.post("/shipments/{tracking_number}/lifecycle", response_model=OperationResult)
    def lifecycle(
        tracking_number: str, simulator: SimulatorDep, body: LifecycleRequest | None = None
    ) -> OperationResult:
        """Send every event that has not been sent yet."""
        body = body or LifecycleRequest()
        deliveries = simulator.lifecycle(
            tracking_number, shuffle=body.shuffle, duplicates=body.duplicates
        )
        return _operation(tracking_number, deliveries)

    @app.post("/bursts", response_model=BurstResult)
    def burst(body: BurstRequest, simulator: SimulatorDep) -> BurstResult:
        """Create many shipments and play out their complete journeys concurrently."""
        summary = simulator.burst(
            shipments=body.shipments,
            scenario=body.scenario,
            register=body.register_shipment,
            shuffle=body.shuffle,
            duplicates=body.duplicates,
            concurrency=body.concurrency,
        )
        return BurstResult(
            shipments=summary.shipments,
            events=summary.events,
            deliveries=summary.deliveries,
            http_attempts=summary.http_attempts,
            undelivered=summary.undelivered,
            results=summary.results,
            duration_seconds=summary.duration_seconds,
            tracking_numbers=summary.tracking_numbers,
        )

    return app
