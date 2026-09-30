"""SQLAlchemy ORM models. The schema itself is managed by Alembic (see migrations/)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Index, MetaData, String, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from parcelpulse_api.domain.status import ShipmentStatus

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


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
    current_status: Mapped[ShipmentStatus] = mapped_column(
        Enum(
            ShipmentStatus,
            native_enum=False,
            length=32,
            create_constraint=True,
            name="current_status_valid",
        ),
        default=ShipmentStatus.CREATED,
    )
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
