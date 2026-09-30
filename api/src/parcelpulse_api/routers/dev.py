"""Development and debugging endpoints.

Mounted under /dev only when ENABLE_DEV_ENDPOINTS=true, which the settings
refuse to combine with ENVIRONMENT=production. They expose internal
bookkeeping that is useful when developing against the carrier simulator and
are not part of the public API contract.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from parcelpulse_api.db import get_session
from parcelpulse_api.models import ReceiptResult, WebhookReceipt
from parcelpulse_api.schemas import Page

router = APIRouter(prefix="/dev", tags=["dev"])


class WebhookReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    provider_event_id: str
    tracking_number: str
    received_at: datetime
    payload_hash: str
    result: ReceiptResult
    is_duplicate: bool
    shipment_id: uuid.UUID | None
    tracking_event_id: uuid.UUID | None
    correlation_id: str | None


@router.get(
    "/webhook-receipts",
    response_model=Page[WebhookReceiptOut],
    summary="List webhook delivery receipts",
)
def list_webhook_receipts(
    session: Annotated[Session, Depends(get_session)],
    provider_event_id: Annotated[str | None, Query(max_length=128)] = None,
    tracking_number: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[WebhookReceiptOut]:
    """Every authenticated delivery attempt, oldest first, including duplicates."""
    conditions = []
    if provider_event_id is not None:
        conditions.append(WebhookReceipt.provider_event_id == provider_event_id)
    if tracking_number is not None:
        conditions.append(WebhookReceipt.tracking_number == tracking_number.strip().upper())

    total = session.execute(
        select(func.count()).select_from(WebhookReceipt).where(*conditions)
    ).scalar_one()
    items = (
        session.execute(
            select(WebhookReceipt)
            .where(*conditions)
            .order_by(WebhookReceipt.received_at, WebhookReceipt.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return Page[WebhookReceiptOut](
        items=[WebhookReceiptOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
