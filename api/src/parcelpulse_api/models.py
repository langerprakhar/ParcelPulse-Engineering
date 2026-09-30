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
    Integer,
    MetaData,
    String,
    Text,
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


class NotificationType(StrEnum):
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELIVERY_EXCEPTION = "DELIVERY_EXCEPTION"


class NotificationChannel(StrEnum):
    EMAIL = "EMAIL"


class NotificationStatus(StrEnum):
    # Written by the API, waiting for the worker.
    PENDING = "PENDING"
    # Claimed by a worker; a send is in flight.
    SENDING = "SENDING"
    SENT = "SENT"
    # The last attempt failed; another is scheduled at next_attempt_at.
    RETRYING = "RETRYING"
    # Gave up after the maximum number of attempts.
    FAILED = "FAILED"


class NotificationPreference(Base):
    """Who to notify about a shipment, and for which events."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("shipment_id", name="uq_notification_preferences_shipment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    # No address means nothing is sent, whatever the flags say.
    email: Mapped[str | None] = mapped_column(String(320))
    notify_out_for_delivery: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_delivered: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_delivery_exception: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Notification(Base):
    """Outbox row: one message owed to one destination because of one tracking event.

    The API inserts rows in the same transaction as the tracking event. The
    notification worker (parcelpulse-worker) owns every later status change.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        # At most one notification of a type per event and destination, no
        # matter how often the carrier redelivers the event.
        UniqueConstraint(
            "tracking_event_id",
            "type",
            "channel",
            "destination",
            name="uq_notifications_event_type_channel_destination",
        ),
        Index("ix_notifications_shipment_id_created_at", "shipment_id", "created_at"),
        Index("ix_notifications_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    tracking_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracking_events.id", ondelete="CASCADE")
    )
    type: Mapped[NotificationType] = mapped_column(_enum(NotificationType, "type_valid"))
    channel: Mapped[NotificationChannel] = mapped_column(
        _enum(NotificationChannel, "channel_valid"), default=NotificationChannel.EMAIL
    )
    destination: Mapped[str] = mapped_column(String(320))
    status: Mapped[NotificationStatus] = mapped_column(
        _enum(NotificationStatus, "status_valid"), default=NotificationStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
