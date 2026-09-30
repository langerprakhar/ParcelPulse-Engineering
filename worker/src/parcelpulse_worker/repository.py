"""Queries against the notification outbox.

Every state change is a single guarded UPDATE, so two workers can never both
believe they own the same notification.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, and_, or_, select, update

from parcelpulse_worker.db import (
    FAILED,
    PENDING,
    RETRYING,
    SENDING,
    SENT,
    notifications,
    shipments,
    tracking_events,
)
from parcelpulse_worker.email_content import NotificationContext

MAX_ERROR_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class ClaimedNotification:
    id: uuid.UUID
    shipment_id: uuid.UUID
    tracking_event_id: uuid.UUID
    type: str
    channel: str
    destination: str
    # Including the attempt that this claim starts.
    attempts: int
    correlation_id: str | None


def claim(
    connection: Connection, notification_id: uuid.UUID, now: datetime
) -> ClaimedNotification | None:
    """Take ownership of a notification that is due, or return None.

    PENDING rows are always due; RETRYING rows are due once ``next_attempt_at``
    has passed. The row moves to SENDING and its attempt counter is incremented
    in the same statement, so of any number of concurrent callers exactly one
    gets the row back.
    """
    row = connection.execute(
        update(notifications)
        .where(
            notifications.c.id == notification_id,
            or_(
                notifications.c.status == PENDING,
                and_(
                    notifications.c.status == RETRYING,
                    notifications.c.next_attempt_at <= now,
                ),
            ),
        )
        .values(
            status=SENDING,
            attempts=notifications.c.attempts + 1,
            claimed_at=now,
            updated_at=now,
        )
        .returning(
            notifications.c.id,
            notifications.c.shipment_id,
            notifications.c.tracking_event_id,
            notifications.c.type,
            notifications.c.channel,
            notifications.c.destination,
            notifications.c.attempts,
            notifications.c.correlation_id,
        )
    ).one_or_none()
    if row is None:
        return None
    return ClaimedNotification(
        id=row.id,
        shipment_id=row.shipment_id,
        tracking_event_id=row.tracking_event_id,
        type=row.type,
        channel=row.channel,
        destination=row.destination,
        attempts=row.attempts,
        correlation_id=row.correlation_id,
    )


def load_context(connection: Connection, claimed: ClaimedNotification) -> NotificationContext:
    row = connection.execute(
        select(
            shipments.c.tracking_number,
            shipments.c.carrier,
            shipments.c.estimated_delivery_at,
            tracking_events.c.event_at,
            tracking_events.c.location,
            tracking_events.c.description,
        )
        .select_from(
            tracking_events.join(shipments, tracking_events.c.shipment_id == shipments.c.id)
        )
        .where(tracking_events.c.id == claimed.tracking_event_id)
    ).one()
    return NotificationContext(
        notification_id=claimed.id,
        notification_type=claimed.type,
        destination=claimed.destination,
        shipment_id=claimed.shipment_id,
        tracking_number=row.tracking_number,
        carrier=row.carrier,
        event_at=row.event_at,
        location=row.location,
        description=row.description,
        estimated_delivery_at=row.estimated_delivery_at,
    )


def _finish(connection: Connection, notification_id: uuid.UUID, **values: object) -> bool:
    """Leave SENDING. Returns False if the row was no longer ours to change."""
    result = connection.execute(
        update(notifications)
        .where(notifications.c.id == notification_id, notifications.c.status == SENDING)
        .values(**values)
    )
    return result.rowcount == 1


def mark_sent(connection: Connection, notification_id: uuid.UUID, now: datetime) -> bool:
    return _finish(
        connection,
        notification_id,
        status=SENT,
        sent_at=now,
        updated_at=now,
        next_attempt_at=None,
        last_error=None,
    )


def mark_retrying(
    connection: Connection,
    notification_id: uuid.UUID,
    *,
    error: str,
    next_attempt_at: datetime,
    now: datetime,
) -> bool:
    return _finish(
        connection,
        notification_id,
        status=RETRYING,
        next_attempt_at=next_attempt_at,
        last_error=error[:MAX_ERROR_LENGTH],
        updated_at=now,
    )


def mark_failed(
    connection: Connection, notification_id: uuid.UUID, *, error: str, now: datetime
) -> bool:
    return _finish(
        connection,
        notification_id,
        status=FAILED,
        next_attempt_at=None,
        last_error=error[:MAX_ERROR_LENGTH],
        updated_at=now,
    )


def get_status(connection: Connection, notification_id: uuid.UUID) -> str | None:
    return connection.execute(
        select(notifications.c.status).where(notifications.c.id == notification_id)
    ).scalar_one_or_none()
