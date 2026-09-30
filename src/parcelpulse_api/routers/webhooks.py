"""Carrier webhook endpoint."""

import json
import logging
import time
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from parcelpulse_api.correlation import get_correlation_id
from parcelpulse_api.db import get_session
from parcelpulse_api.errors import AppError, UnauthorizedError
from parcelpulse_api.models import utcnow
from parcelpulse_api.queue import NotificationPublisher
from parcelpulse_api.schemas import CarrierEventPayload, WebhookResult
from parcelpulse_api.security import SIGNATURE_HEADER, InvalidSignatureError, verify_signature
from parcelpulse_api.services.webhooks import IngestOutcome, ingest_carrier_event

logger = logging.getLogger("parcelpulse.webhooks")

router = APIRouter(tags=["webhooks"])


class InvalidWebhookSignatureError(UnauthorizedError):
    code = "invalid_webhook_signature"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


async def authenticated_body(request: Request) -> bytes:
    """Return the raw request body after checking its size and carrier signature."""
    settings = request.app.state.settings
    body = await request.body()
    if len(body) > settings.webhook_max_body_bytes:
        raise PayloadTooLargeError(
            "Webhook body is too large",
            details={"max_bytes": settings.webhook_max_body_bytes},
        )

    if settings.webhook_signature_required:
        try:
            verify_signature(
                secret=settings.webhook_signing_secret.get_secret_value(),
                body=body,
                header=request.headers.get(SIGNATURE_HEADER),
                now=time.time(),
                tolerance_seconds=settings.webhook_signature_tolerance_seconds,
            )
        except InvalidSignatureError as exc:
            # The reason is logged for operators; callers only learn that it failed.
            logger.warning("rejected carrier webhook", extra={"reason": str(exc)})
            raise InvalidWebhookSignatureError("Webhook signature verification failed") from None
    return body


@router.post(
    "/webhooks/carrier",
    response_model=WebhookResult,
    summary="Receive a carrier tracking event",
    responses={
        401: {"description": "Missing, stale or invalid signature"},
        413: {"description": "Body larger than the configured limit"},
        422: {"description": "Payload failed validation"},
    },
)
def receive_carrier_event(
    payload: CarrierEventPayload,
    body: Annotated[bytes, Depends(authenticated_body)],
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> WebhookResult:
    """Ingest one carrier event.

    The endpoint is idempotent on `(provider, event_id)`: a redelivered event is
    acknowledged with `result: DUPLICATE` and has no further effect. Every
    accepted delivery returns 200 so that carriers stop retrying, including
    deliveries for tracking numbers ParcelPulse does not track
    (`result: UNKNOWN_SHIPMENT`).
    """
    settings = request.app.state.settings
    raw_payload: dict[str, Any] = json.loads(body)

    with session.begin():
        outcome = ingest_carrier_event(
            session,
            payload,
            raw_payload=raw_payload,
            received_at=utcnow(),
            correlation_id=get_correlation_id(),
            max_future_skew=timedelta(seconds=settings.webhook_max_future_skew_seconds),
        )

    _publish_notifications(request.app.state.notification_publisher, outcome)

    logger.info(
        "carrier webhook handled",
        extra={
            "result": outcome.result.value,
            "provider": payload.provider,
            "provider_event_id": payload.event_id,
            "event_type": payload.event_type.value,
            "shipment_id": str(outcome.shipment_id) if outcome.shipment_id else None,
            "tracking_event_id": (
                str(outcome.tracking_event_id) if outcome.tracking_event_id else None
            ),
            "shipment_status": outcome.shipment_status.value if outcome.shipment_status else None,
            "status_changed": outcome.status_changed,
            "arrived_out_of_order": outcome.arrived_out_of_order,
            "notifications": len(outcome.notification_ids),
        },
    )
    return WebhookResult(
        result=outcome.result,
        duplicate=outcome.duplicate,
        receipt_id=outcome.receipt_id,
        shipment_id=outcome.shipment_id,
        tracking_event_id=outcome.tracking_event_id,
        shipment_status=outcome.shipment_status,
    )


def _publish_notifications(publisher: NotificationPublisher, outcome: IngestOutcome) -> None:
    """Wake the worker for each outbox row this delivery committed.

    Runs after commit, so the worker can never see a message for a row that does
    not exist yet. A publish failure does not fail the webhook: the row is
    already durable as PENDING and the worker's sweeper will find it.
    """
    for notification_id in outcome.notification_ids:
        try:
            publisher.publish(notification_id, correlation_id=get_correlation_id())
        except Exception:
            logger.exception(
                "could not publish notification; it stays PENDING for the sweeper",
                extra={"notification_id": str(notification_id)},
            )
