"""Database access.

The schema is owned and migrated by parcelpulse-api. The tables below mirror
only the columns this worker reads or writes; they are used to build queries
and, in this repository's tests, to create a throwaway schema. The worker never
creates or alters tables in a real environment.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

shipments = Table(
    "shipments",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tracking_number", String(40), nullable=False),
    Column("carrier", String(32), nullable=False),
    Column("current_status", String(32), nullable=False),
    Column("estimated_delivery_at", DateTime(timezone=True)),
)

tracking_events = Table(
    "tracking_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("shipment_id", Uuid, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
    Column("event_type", String(32), nullable=False),
    Column("event_at", DateTime(timezone=True), nullable=False),
    Column("location", JSONB),
    Column("description", String(500)),
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("shipment_id", Uuid, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
    Column(
        "tracking_event_id",
        Uuid,
        ForeignKey("tracking_events.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("type", String(32), nullable=False),
    Column("channel", String(32), nullable=False),
    Column("destination", String(320), nullable=False),
    Column("status", String(32), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("claimed_at", DateTime(timezone=True)),
    Column("next_attempt_at", DateTime(timezone=True)),
    Column("sent_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("correlation_id", String(64)),
)

# Notification statuses, as written by parcelpulse-api and by this worker.
PENDING = "PENDING"
SENDING = "SENDING"
SENT = "SENT"
RETRYING = "RETRYING"
FAILED = "FAILED"


def create_db_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)
