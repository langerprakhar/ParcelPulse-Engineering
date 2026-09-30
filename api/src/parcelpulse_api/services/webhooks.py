"""Carrier webhook ingestion.

One call to :func:`ingest_carrier_event` handles one webhook delivery inside the
caller's transaction. Everything the delivery causes - the tracking event, the
shipment state change, owed notifications and the audit receipt - commits
together or not at all,
which is what makes a carrier retry safe:

* If the first attempt failed before commit, nothing was written and the retry
  is processed as a new event.
* If the first attempt committed, the retry hits the unique constraint on
  ``(provider, provider_event_id)``, is recorded as a duplicate receipt and
  changes nothing else.

See docs/webhook-idempotency.md.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from parcelpulse_api.domain.state import EventFacts, arrived_out_of_order, derive_state
from parcelpulse_api.domain.status import ShipmentStatus
from parcelpulse_api.errors import AppError
from parcelpulse_api.models import ReceiptResult, Shipment, TrackingEvent, WebhookReceipt
from parcelpulse_api.schemas import CarrierEventPayload
from parcelpulse_api.security import hash_payload
from parcelpulse_api.services.notifications import plan_notifications

logger = logging.getLogger("parcelpulse.webhooks")


class EventTimeInFutureError(AppError):
    status_code = 422
    code = "event_time_in_future"


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    result: ReceiptResult
    receipt_id: uuid.UUID
    shipment_id: uuid.UUID | None = None
    tracking_event_id: uuid.UUID | None = None
    shipment_status: ShipmentStatus | None = None
    status_changed: bool = False
    arrived_out_of_order: bool = False
    # Outbox rows written by this delivery; the caller publishes them after commit.
    notification_ids: tuple[uuid.UUID, ...] = ()

    @property
    def duplicate(self) -> bool:
        return self.result in (ReceiptResult.DUPLICATE, ReceiptResult.DUPLICATE_PAYLOAD_MISMATCH)


def ingest_carrier_event(
    session: Session,
    payload: CarrierEventPayload,
    *,
    raw_payload: dict[str, Any],
    received_at: datetime,
    correlation_id: str | None = None,
    max_future_skew: timedelta = timedelta(hours=1),
) -> IngestOutcome:
    """Record one carrier webhook delivery. Must run inside a transaction."""
    if payload.occurred_at > received_at + max_future_skew:
        raise EventTimeInFutureError(
            "occurred_at is too far in the future",
            details={"max_future_skew_seconds": int(max_future_skew.total_seconds())},
        )

    payload_hash = hash_payload(raw_payload)

    def record_receipt(
        result: ReceiptResult,
        *,
        shipment_id: uuid.UUID | None = None,
        tracking_event_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        receipt = WebhookReceipt(
            id=uuid.uuid4(),
            provider=payload.provider,
            provider_event_id=payload.event_id,
            tracking_number=payload.tracking_number,
            received_at=received_at,
            payload_hash=payload_hash,
            result=result,
            is_duplicate=result
            in (ReceiptResult.DUPLICATE, ReceiptResult.DUPLICATE_PAYLOAD_MISMATCH),
            shipment_id=shipment_id,
            tracking_event_id=tracking_event_id,
            correlation_id=correlation_id,
        )
        session.add(receipt)
        return receipt.id

    # Lock the shipment row: deliveries for the same shipment are processed one
    # at a time, so state derivation always sees a complete set of events.
    shipment = session.execute(
        select(Shipment)
        .where(
            Shipment.carrier == payload.provider,
            Shipment.tracking_number == payload.tracking_number,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if shipment is None:
        receipt_id = record_receipt(ReceiptResult.UNKNOWN_SHIPMENT)
        return IngestOutcome(result=ReceiptResult.UNKNOWN_SHIPMENT, receipt_id=receipt_id)

    known = _event_facts(session, shipment.id)
    candidate = EventFacts(
        id=uuid.uuid4(),
        event_type=payload.event_type,
        event_at=payload.occurred_at,
        received_at=received_at,
        estimated_delivery_at=payload.estimated_delivery_at,
    )
    state = derive_state([*known, candidate])
    out_of_order = arrived_out_of_order(candidate, known)
    status_changed = state.status != shipment.current_status

    # The unique constraint is the single source of truth for "have we stored
    # this carrier event?". ON CONFLICT DO NOTHING makes the check and the write
    # one atomic statement; a concurrent delivery of the same event waits on the
    # index entry and then sees the conflict.
    inserted_id = session.execute(
        pg_insert(TrackingEvent)
        .values(
            id=candidate.id,
            shipment_id=shipment.id,
            provider=payload.provider,
            provider_event_id=payload.event_id,
            event_type=payload.event_type,
            event_at=payload.occurred_at,
            received_at=received_at,
            location=payload.location.model_dump(exclude_none=True) if payload.location else None,
            description=payload.description,
            estimated_delivery_at=payload.estimated_delivery_at,
            payload=raw_payload,
            payload_hash=payload_hash,
            arrived_out_of_order=out_of_order,
            changed_status=status_changed,
            status_after=state.status,
            correlation_id=correlation_id,
        )
        .on_conflict_do_nothing(constraint="uq_tracking_events_provider_event_id")
        .returning(TrackingEvent.id)
    ).scalar_one_or_none()

    if inserted_id is None:
        return _record_duplicate(session, payload, payload_hash, shipment, record_receipt)

    shipment.current_status = state.status
    shipment.last_event_at = state.last_event_at
    shipment.estimated_delivery_at = state.estimated_delivery_at

    notification_ids = plan_notifications(
        session,
        shipment_id=shipment.id,
        tracking_event_id=candidate.id,
        event_type=payload.event_type,
        became_current_status=status_changed and state.deciding_event_id == candidate.id,
        correlation_id=correlation_id,
    )

    receipt_id = record_receipt(
        ReceiptResult.PROCESSED, shipment_id=shipment.id, tracking_event_id=candidate.id
    )
    return IngestOutcome(
        result=ReceiptResult.PROCESSED,
        receipt_id=receipt_id,
        shipment_id=shipment.id,
        tracking_event_id=candidate.id,
        shipment_status=state.status,
        status_changed=status_changed,
        arrived_out_of_order=out_of_order,
        notification_ids=tuple(notification_ids),
    )


def _event_facts(session: Session, shipment_id: uuid.UUID) -> list[EventFacts]:
    rows = session.execute(
        select(
            TrackingEvent.id,
            TrackingEvent.event_type,
            TrackingEvent.event_at,
            TrackingEvent.received_at,
            TrackingEvent.estimated_delivery_at,
        ).where(TrackingEvent.shipment_id == shipment_id)
    ).all()
    return [
        EventFacts(
            id=row.id,
            event_type=row.event_type,
            event_at=row.event_at,
            received_at=row.received_at,
            estimated_delivery_at=row.estimated_delivery_at,
        )
        for row in rows
    ]


def _record_duplicate(
    session: Session,
    payload: CarrierEventPayload,
    payload_hash: str,
    shipment: Shipment,
    record_receipt: Callable[..., uuid.UUID],
) -> IngestOutcome:
    """The event is already stored: write an audit receipt and change nothing else."""
    original = session.execute(
        select(TrackingEvent).where(
            TrackingEvent.provider == payload.provider,
            TrackingEvent.provider_event_id == payload.event_id,
        )
    ).scalar_one()

    result = ReceiptResult.DUPLICATE
    if original.payload_hash != payload_hash:
        # Same event id, different content. The stored event is kept as-is: the
        # carrier contract says an event id identifies one immutable event.
        result = ReceiptResult.DUPLICATE_PAYLOAD_MISMATCH
        logger.warning(
            "duplicate carrier event id with a different payload; keeping the original",
            extra={
                "provider": payload.provider,
                "provider_event_id": payload.event_id,
                "tracking_event_id": str(original.id),
            },
        )

    receipt_id = record_receipt(
        result, shipment_id=original.shipment_id, tracking_event_id=original.id
    )
    return IngestOutcome(
        result=result,
        receipt_id=receipt_id,
        shipment_id=original.shipment_id,
        tracking_event_id=original.id,
        shipment_status=shipment.current_status if original.shipment_id == shipment.id else None,
    )
