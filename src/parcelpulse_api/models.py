"""SQLAlchemy ORM models. The schema itself is managed by Alembic (see migrations/)."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from parcelpulse_api.domain.status import EventType, ShipmentStatus

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(enum_class: type[StrEnum], constraint_name: str) -> Enum:
    """Store an enum as a VARCHAR guarded by a CHECK constraint."""
    return Enum(
        enum_class, native_enum=False, length=32, create_constraint=True, name=constraint_name
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("carrier", "tracking_number", name="uq_shipments_carrier_tracking_number"),
        Index("ix_shipments_tracking_number", "tracking_number"),
        Index("ix_shipments_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tracking_number: Mapped[str] = mapped_column(String(40))
    carrier: Mapped[str] = mapped_column(String(32))
    # Derived from tracking events; see parcelpulse_api.domain.state.
    current_status: Mapped[ShipmentStatus] = mapped_column(
        _enum(ShipmentStatus, "current_status_valid"), default=ShipmentStatus.CREATED
    )
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TrackingEvent(Base):
    """One carrier event. Rows are immutable once written."""

    __tablename__ = "tracking_events"
    __table_args__ = (
        # The idempotency key: a carrier event is stored at most once.
        UniqueConstraint(
            "provider", "provider_event_id", name="uq_tracking_events_provider_event_id"
        ),
        Index("ix_tracking_events_shipment_id_event_at", "shipment_id", "event_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[EventType] = mapped_column(_enum(EventType, "event_type_valid"))
    # When the carrier says it happened, and when we learned about it.
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(String(500))
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(String(64))

    # Processing metadata, recorded at ingestion time.
    arrived_out_of_order: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_status: Mapped[bool] = mapped_column(Boolean, default=False)
    status_after: Mapped[ShipmentStatus] = mapped_column(
        _enum(ShipmentStatus, "status_after_valid")
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64))


class ReceiptResult(StrEnum):
    PROCESSED = "PROCESSED"
    DUPLICATE = "DUPLICATE"
    # Same provider event id as a stored event, but a different body.
    DUPLICATE_PAYLOAD_MISMATCH = "DUPLICATE_PAYLOAD_MISMATCH"
    UNKNOWN_SHIPMENT = "UNKNOWN_SHIPMENT"


class WebhookReceipt(Base):
    """Audit log: one row per authenticated, well-formed webhook delivery attempt."""

    __tablename__ = "webhook_receipts"
    __table_args__ = (
        Index("ix_webhook_receipts_provider_event_id", "provider", "provider_event_id"),
        Index("ix_webhook_receipts_received_at", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str] = mapped_column(String(128))
    tracking_number: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[ReceiptResult] = mapped_column(_enum(ReceiptResult, "result_valid"))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shipments.id", ondelete="SET NULL")
    )
    # The event this delivery created, or the original it duplicates.
    tracking_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tracking_events.id", ondelete="SET NULL")
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64))
