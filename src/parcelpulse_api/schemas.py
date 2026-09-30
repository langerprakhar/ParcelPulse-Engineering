"""Request and response schemas for the public API."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from parcelpulse_api.domain.status import ShipmentStatus

TRACKING_NUMBER_PATTERN = r"^[A-Z0-9]{6,40}$"
CARRIER_CODE_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,31}$"


def _normalize_tracking_number(value: object) -> object:
    # Users paste tracking numbers with spaces and dashes; carriers ignore both.
    if isinstance(value, str):
        return value.strip().replace(" ", "").replace("-", "").upper()
    return value


def _normalize_carrier(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


TrackingNumber = Annotated[
    str,
    BeforeValidator(_normalize_tracking_number),
    StringConstraints(pattern=TRACKING_NUMBER_PATTERN),
]
CarrierCode = Annotated[
    str,
    BeforeValidator(_normalize_carrier),
    StringConstraints(pattern=CARRIER_CODE_PATTERN),
]


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_number: TrackingNumber = Field(examples=["SC4F7K2M9Q1X"])
    carrier: CarrierCode = Field(examples=["simcarrier"])


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tracking_number: str
    carrier: str
    current_status: ShipmentStatus
    estimated_delivery_at: datetime | None
    last_event_at: datetime | None
    created_at: datetime
    updated_at: datetime


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class CarrierOut(BaseModel):
    code: str


class CarrierList(BaseModel):
    items: list[CarrierOut]
