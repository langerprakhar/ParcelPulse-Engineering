"""Shipment registration and lookup endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from parcelpulse_api.db import get_session
from parcelpulse_api.domain.status import ShipmentStatus
from parcelpulse_api.schemas import (
    CARRIER_CODE_PATTERN,
    CarrierList,
    CarrierOut,
    Page,
    ShipmentCreate,
    ShipmentOut,
    TrackingNumber,
)
from parcelpulse_api.services import shipments as shipment_service

router = APIRouter(tags=["shipments"])

SessionDep = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100, description="Page size")]
Offset = Annotated[int, Query(ge=0, description="Number of items to skip")]


@router.get("/carriers", response_model=CarrierList, summary="List supported carriers")
def list_carriers(request: Request) -> CarrierList:
    carriers = request.app.state.settings.supported_carriers
    return CarrierList(items=[CarrierOut(code=code) for code in carriers])


@router.post(
    "/shipments",
    response_model=ShipmentOut,
    status_code=201,
    summary="Register a shipment to track",
    responses={409: {"description": "The shipment is already tracked"}},
)
def create_shipment(
    body: ShipmentCreate, request: Request, response: Response, session: SessionDep
) -> ShipmentOut:
    with session.begin():
        shipment = shipment_service.create_shipment(
            session,
            tracking_number=body.tracking_number,
            carrier=body.carrier,
            supported_carriers=request.app.state.settings.supported_carriers,
        )
    response.headers["Location"] = f"/shipments/{shipment.id}"
    return ShipmentOut.model_validate(shipment)


@router.get("/shipments", response_model=Page[ShipmentOut], summary="List shipments")
def list_shipments(
    session: SessionDep,
    limit: Limit = 20,
    offset: Offset = 0,
    status: Annotated[ShipmentStatus | None, Query(description="Filter by status")] = None,
) -> Page[ShipmentOut]:
    """Newest shipments first."""
    items, total = shipment_service.list_shipments(
        session, limit=limit, offset=offset, status=status
    )
    return Page[ShipmentOut](
        items=[ShipmentOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/shipments/by-tracking/{tracking_number}",
    response_model=ShipmentOut,
    summary="Look up a shipment by tracking number",
    responses={409: {"description": "The tracking number exists for several carriers"}},
)
def get_shipment_by_tracking_number(
    tracking_number: Annotated[TrackingNumber, Path()],
    session: SessionDep,
    carrier: Annotated[
        str | None,
        Query(pattern=CARRIER_CODE_PATTERN, description="Disambiguate by carrier code"),
    ] = None,
) -> ShipmentOut:
    shipment = shipment_service.get_shipment_by_tracking_number(session, tracking_number, carrier)
    return ShipmentOut.model_validate(shipment)


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut, summary="Get a shipment")
def get_shipment(shipment_id: uuid.UUID, session: SessionDep) -> ShipmentOut:
    return ShipmentOut.model_validate(shipment_service.get_shipment(session, shipment_id))
