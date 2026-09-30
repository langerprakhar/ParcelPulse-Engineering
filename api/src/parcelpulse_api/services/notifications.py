"""Notification preferences and the notification outbox.

Notification policy
-------------------
A notification is owed when a newly stored tracking event

1. is of a notifiable type (OUT_FOR_DELIVERY, DELIVERED, DELIVERY_EXCEPTION),
2. *became the shipment's current status* when it was ingested, and
3. the shipment has an email address with that notification type enabled.

Rule 2 keeps history quiet: an OUT_FOR_DELIVERY event that arrives after the
parcel was delivered is added to the timeline but nobody is told the parcel is
"out for delivery". Duplicate deliveries never reach this code at all, because
they do not store a new event.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from parcelpulse_api.domain.status import EventType
from parcelpulse_api.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
    NotificationType,
    utcnow,
)
from parcelpulse_api.services.shipments import get_shipment

NOTIFICATION_FOR_EVENT: dict[EventType, NotificationType] = {
    EventType.OUT_FOR_DELIVERY: NotificationType.OUT_FOR_DELIVERY,
    EventType.DELIVERED: NotificationType.DELIVERED,
    EventType.DELIVERY_EXCEPTION: NotificationType.DELIVERY_EXCEPTION,
}


def _is_enabled(preference: NotificationPreference, notification_type: NotificationType) -> bool:
    return {
        NotificationType.OUT_FOR_DELIVERY: preference.notify_out_for_delivery,
        NotificationType.DELIVERED: preference.notify_delivered,
        NotificationType.DELIVERY_EXCEPTION: preference.notify_delivery_exception,
    }[notification_type]


def find_preference(session: Session, shipment_id: uuid.UUID) -> NotificationPreference | None:
    return session.execute(
        select(NotificationPreference).where(NotificationPreference.shipment_id == shipment_id)
    ).scalar_one_or_none()


def get_preference(session: Session, shipment_id: uuid.UUID) -> NotificationPreference:
    """The stored preference, or the defaults (no address, everything enabled)."""
    get_shipment(session, shipment_id)
    stored = find_preference(session, shipment_id)
    if stored is not None:
        return stored
    return NotificationPreference(
        shipment_id=shipment_id,
        email=None,
        notify_out_for_delivery=True,
        notify_delivered=True,
        notify_delivery_exception=True,
    )


def save_preference(
    session: Session,
    shipment_id: uuid.UUID,
    *,
    email: str | None,
    notify_out_for_delivery: bool = True,
    notify_delivered: bool = True,
    notify_delivery_exception: bool = True,
) -> NotificationPreference:
    get_shipment(session, shipment_id)
    values = {
        "email": email,
        "notify_out_for_delivery": notify_out_for_delivery,
        "notify_delivered": notify_delivered,
        "notify_delivery_exception": notify_delivery_exception,
    }
    # Upsert so that two concurrent saves cannot collide on the unique constraint.
    session.execute(
        pg_insert(NotificationPreference)
        .values(id=uuid.uuid4(), shipment_id=shipment_id, **values)
        .on_conflict_do_update(
            constraint="uq_notification_preferences_shipment_id",
            set_={**values, "updated_at": utcnow()},
        )
    )
    return session.execute(
        select(NotificationPreference)
        .where(NotificationPreference.shipment_id == shipment_id)
        .execution_options(populate_existing=True)
    ).scalar_one()


def plan_notifications(
    session: Session,
    *,
    shipment_id: uuid.UUID,
    tracking_event_id: uuid.UUID,
    event_type: EventType,
    became_current_status: bool,
    correlation_id: str | None = None,
) -> list[uuid.UUID]:
    """Write outbox rows for a newly stored event. Returns the ids to publish."""
    notification_type = NOTIFICATION_FOR_EVENT.get(event_type)
    if notification_type is None or not became_current_status:
        return []

    preference = find_preference(session, shipment_id)
    if preference is None or not preference.email:
        return []
    if not _is_enabled(preference, notification_type):
        return []

    # The unique constraint is a backstop: should this ever run twice for one
    # event, the second insert is a no-op rather than a second email.
    inserted_id = session.execute(
        pg_insert(Notification)
        .values(
            id=uuid.uuid4(),
            shipment_id=shipment_id,
            tracking_event_id=tracking_event_id,
            type=notification_type,
            channel=NotificationChannel.EMAIL,
            destination=preference.email,
            status=NotificationStatus.PENDING,
            correlation_id=correlation_id,
        )
        .on_conflict_do_nothing(constraint="uq_notifications_event_type_channel_destination")
        .returning(Notification.id)
    ).scalar_one_or_none()
    return [inserted_id] if inserted_id is not None else []


def list_notifications(
    session: Session, shipment_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Notification], int]:
    get_shipment(session, shipment_id)
    total = session.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.shipment_id == shipment_id)
    ).scalar_one()
    items = (
        session.execute(
            select(Notification)
            .where(Notification.shipment_id == shipment_id)
            .order_by(Notification.created_at.desc(), Notification.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(items), total
