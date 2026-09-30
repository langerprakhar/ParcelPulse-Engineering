"""create tracking events and webhook receipts

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT_TYPES = (
    "LABEL_CREATED",
    "IN_TRANSIT",
    "AT_DISTRIBUTION_CENTER",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "DELIVERY_EXCEPTION",
    "RETURNED",
)
SHIPMENT_STATUSES = ("CREATED", *EVENT_TYPES)
RECEIPT_RESULTS = ("PROCESSED", "DUPLICATE", "DUPLICATE_PAYLOAD_MISMATCH", "UNKNOWN_SHIPMENT")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def upgrade() -> None:
    op.create_table(
        "tracking_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", postgresql.JSONB(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("arrived_out_of_order", sa.Boolean(), nullable=False),
        sa.Column("changed_status", sa.Boolean(), nullable=False),
        sa.Column("status_after", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tracking_events"),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipments.id"],
            name="fk_tracking_events_shipment_id_shipments",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_tracking_events_provider_event_id"
        ),
        sa.CheckConstraint(
            _in("event_type", EVENT_TYPES), name="ck_tracking_events_event_type_valid"
        ),
        sa.CheckConstraint(
            _in("status_after", SHIPMENT_STATUSES), name="ck_tracking_events_status_after_valid"
        ),
    )
    op.create_index(
        "ix_tracking_events_shipment_id_event_at", "tracking_events", ["shipment_id", "event_at"]
    )

    op.create_table(
        "webhook_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column("tracking_number", sa.String(length=40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=True),
        sa.Column("tracking_event_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_receipts"),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipments.id"],
            name="fk_webhook_receipts_shipment_id_shipments",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tracking_event_id"],
            ["tracking_events.id"],
            name="fk_webhook_receipts_tracking_event_id_tracking_events",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(_in("result", RECEIPT_RESULTS), name="ck_webhook_receipts_result_valid"),
    )
    op.create_index(
        "ix_webhook_receipts_provider_event_id",
        "webhook_receipts",
        ["provider", "provider_event_id"],
    )
    op.create_index("ix_webhook_receipts_received_at", "webhook_receipts", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_webhook_receipts_received_at", table_name="webhook_receipts")
    op.drop_index("ix_webhook_receipts_provider_event_id", table_name="webhook_receipts")
    op.drop_table("webhook_receipts")
    op.drop_index("ix_tracking_events_shipment_id_event_at", table_name="tracking_events")
    op.drop_table("tracking_events")
