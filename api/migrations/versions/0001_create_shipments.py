"""create shipments

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHIPMENT_STATUSES = (
    "CREATED",
    "LABEL_CREATED",
    "IN_TRANSIT",
    "AT_DISTRIBUTION_CENTER",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "DELIVERY_EXCEPTION",
    "RETURNED",
)


def upgrade() -> None:
    statuses = ", ".join(f"'{status}'" for status in SHIPMENT_STATUSES)
    op.create_table(
        "shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tracking_number", sa.String(length=40), nullable=False),
        sa.Column("carrier", sa.String(length=32), nullable=False),
        sa.Column("current_status", sa.String(length=32), nullable=False),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_shipments"),
        sa.UniqueConstraint(
            "carrier", "tracking_number", name="uq_shipments_carrier_tracking_number"
        ),
        sa.CheckConstraint(
            f"current_status IN ({statuses})", name="ck_shipments_current_status_valid"
        ),
    )
    op.create_index("ix_shipments_tracking_number", "shipments", ["tracking_number"])
    op.create_index("ix_shipments_created_at", "shipments", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_shipments_created_at", table_name="shipments")
    op.drop_index("ix_shipments_tracking_number", table_name="shipments")
    op.drop_table("shipments")
