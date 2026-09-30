"""Notification preferences and delivery history for a shipment."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from parcelpulse_api.db import get_session
from parcelpulse_api.schemas import (
    NotificationOut,
    NotificationPreferenceIn,
    NotificationPreferenceOut,
    Page,
)
from parcelpulse_api.services import notifications as notification_service

router = APIRouter(tags=["notifications"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/shipments/{shipment_id}/notification-preferences",
    response_model=NotificationPreferenceOut,
    summary="Get notification preferences",
)
def get_notification_preferences(
    shipment_id: uuid.UUID, session: SessionDep
) -> NotificationPreferenceOut:
    """Returns the defaults (no address, every notification enabled) until saved."""
    preference = notification_service.get_preference(session, shipment_id)
    return NotificationPreferenceOut.model_validate(preference)


@router.put(
    "/shipments/{shipment_id}/notification-preferences",
    response_model=NotificationPreferenceOut,
    summary="Replace notification preferences",
)
def put_notification_preferences(
    shipment_id: uuid.UUID, body: NotificationPreferenceIn, session: SessionDep
) -> NotificationPreferenceOut:
    """Applies to events received from now on; already queued notifications are unaffected."""
    with session.begin():
        preference = notification_service.save_preference(
            session,
            shipment_id,
            email=body.email,
            notify_out_for_delivery=body.notify_out_for_delivery,
            notify_delivered=body.notify_delivered,
            notify_delivery_exception=body.notify_delivery_exception,
        )
    return NotificationPreferenceOut.model_validate(preference)


@router.get(
    "/shipments/{shipment_id}/notifications",
    response_model=Page[NotificationOut],
    summary="List notifications for a shipment",
)
def list_notifications(
    shipment_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    offset: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
) -> Page[NotificationOut]:
    """Newest first. `status` and `attempts` are maintained by the notification worker."""
    items, total = notification_service.list_notifications(
        session, shipment_id, limit=limit, offset=offset
    )
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
