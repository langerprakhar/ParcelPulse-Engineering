"""create notification preferences and the notification outbox

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTIFICATION_TYPES = ("OUT_FOR_DELIVERY", "DELIVERED", "DELIVERY_EXCEPTION")
NOTIFICATION_CHANNELS = ("EMAIL",)
NOTIFICATION_STATUSES = ("PENDING", "SENDING", "SENT", "RETRYING", "FAILED")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("notify_out_for_delivery", sa.Boolean(), nullable=False),
        sa.Column("notify_delivered", sa.Boolean(), nullable=False),
        sa.Column("notify_delivery_exception", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notification_preferences"),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipments.id"],
            name="fk_notification_preferences_shipment_id_shipments",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("shipment_id", name="uq_notification_preferences_shipment_id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("tracking_event_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("destination", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipments.id"],
            name="fk_notifications_shipment_id_shipments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tracking_event_id"],
            ["tracking_events.id"],
            name="fk_notifications_tracking_event_id_tracking_events",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tracking_event_id",
            "type",
            "channel",
            "destination",
            name="uq_notifications_event_type_channel_destination",
        ),
        sa.CheckConstraint(_in("type", NOTIFICATION_TYPES), name="ck_notifications_type_valid"),
        sa.CheckConstraint(
            _in("channel", NOTIFICATION_CHANNELS), name="ck_notifications_channel_valid"
        ),
        sa.CheckConstraint(
            _in("status", NOTIFICATION_STATUSES), name="ck_notifications_status_valid"
        ),
    )
    op.create_index(
        "ix_notifications_shipment_id_created_at", "notifications", ["shipment_id", "created_at"]
    )
    op.create_index(
        "ix_notifications_status_next_attempt_at", "notifications", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_status_next_attempt_at", table_name="notifications")
    op.drop_index("ix_notifications_shipment_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
