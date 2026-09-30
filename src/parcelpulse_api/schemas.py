"""Request and response schemas for the public API."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

from parcelpulse_api.domain.status import EventType, ShipmentStatus
from parcelpulse_api.models import ReceiptResult

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


# --- Carrier webhooks -------------------------------------------------------

ShortText = Annotated[str, StringConstraints(max_length=120)]


class EventLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    facility: ShortText | None = None
    city: ShortText | None = None
    region: ShortText | None = None
    country: ShortText | None = None


class CarrierEventPayload(BaseModel):
    """The webhook body a carrier sends for one tracking event.

    Unknown fields are accepted and kept in the stored payload: carriers add
    fields without notice and we must not reject their deliveries for it.
    """

    model_config = ConfigDict(extra="allow")

    provider: CarrierCode = Field(description="Carrier code", examples=["simcarrier"])
    event_id: Annotated[
        str, StringConstraints(min_length=1, max_length=128, pattern=r"^[!-~]+$")
    ] = Field(description="Carrier-assigned id, unique per event. The idempotency key.")
    tracking_number: TrackingNumber
    event_type: EventType
    occurred_at: AwareDatetime = Field(
        description="When the event happened, by the carrier's clock. Must carry a UTC offset."
    )
    location: EventLocation | None = None
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    estimated_delivery_at: AwareDatetime | None = None


class WebhookResult(BaseModel):
    result: ReceiptResult
    duplicate: bool
    receipt_id: uuid.UUID
    shipment_id: uuid.UUID | None
    tracking_event_id: uuid.UUID | None
    shipment_status: ShipmentStatus | None


class TrackingEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shipment_id: uuid.UUID
    provider: str
    provider_event_id: str
    event_type: EventType
    event_at: datetime
    received_at: datetime
    location: dict[str, Any] | None
    description: str | None
    estimated_delivery_at: datetime | None
    arrived_out_of_order: bool
    changed_status: bool
    status_after: ShipmentStatus
