"""Delivering one notification.

``deliver_notification`` is safe to call any number of times, from any number
of workers, for the same notification id:

1. **Claim.** One guarded UPDATE moves the row from PENDING (or a due RETRYING)
   to SENDING. Only the caller that wins the claim continues; everyone else
   returns SKIPPED. The claim is committed before anything is sent.
2. **Send.** The email goes out through the configured sender.
3. **Record.** The row moves to SENT, or to RETRYING with a backoff, or to
   FAILED when the error is permanent or the attempts are used up.

If the process dies between steps 2 and 3 the row stays in SENDING. The sweeper
later returns it to RETRYING, so in that one window a message can be sent
twice; its Message-ID is stable so receiving systems can drop the repeat.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import Engine

from parcelpulse_worker import repository
from parcelpulse_worker.config import Settings
from parcelpulse_worker.email_content import render_email
from parcelpulse_worker.retry import backoff_delay
from parcelpulse_worker.senders import EmailSender, PermanentDeliveryError

logger = logging.getLogger("parcelpulse.worker.delivery")

SUPPORTED_CHANNEL = "EMAIL"


class DeliveryResult(StrEnum):
    SENT = "SENT"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED = "FAILED"
    # Nothing to do: unknown id, already handled, in flight elsewhere or not yet due.
    SKIPPED = "SKIPPED"


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    result: DeliveryResult
    attempts: int = 0
    # Set for RETRY_SCHEDULED: when the next attempt becomes due.
    retry_delay: timedelta | None = None
    detail: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def deliver_notification(
    notification_id: uuid.UUID,
    *,
    engine: Engine,
    sender: EmailSender,
    settings: Settings,
    clock: Callable[[], datetime] = utcnow,
) -> DeliveryOutcome:
    with engine.begin() as connection:
        claimed = repository.claim(connection, notification_id, clock())
        if claimed is None:
            status = repository.get_status(connection, notification_id)
            logger.info(
                "notification not claimed",
                extra={"notification_id": str(notification_id), "status": status},
            )
            return DeliveryOutcome(DeliveryResult.SKIPPED, detail=f"status={status}")
        context = repository.load_context(connection, claimed)

    log_fields = {
        "notification_id": str(claimed.id),
        "notification_type": claimed.type,
        "attempt": claimed.attempts,
    }

    try:
        if claimed.channel != SUPPORTED_CHANNEL:
            raise PermanentDeliveryError(f"unsupported channel '{claimed.channel}'")
        message = render_email(
            context, sender=settings.email_from, web_base_url=settings.web_base_url
        )
        sender.send(message)
    except PermanentDeliveryError as error:
        with engine.begin() as connection:
            repository.mark_failed(connection, claimed.id, error=_describe(error), now=clock())
        logger.error(
            "notification failed permanently", extra={**log_fields, "error": _describe(error)}
        )
        return DeliveryOutcome(DeliveryResult.FAILED, claimed.attempts, detail=_describe(error))
    except Exception as error:
        return _record_failed_attempt(claimed, error, engine, settings, clock, log_fields)

    with engine.begin() as connection:
        recorded = repository.mark_sent(connection, claimed.id, clock())
    if not recorded:
        # The lease expired while we were sending and the sweeper took the row back.
        logger.warning("notification was sent but no longer in SENDING", extra=log_fields)
    logger.info("notification sent", extra=log_fields)
    return DeliveryOutcome(DeliveryResult.SENT, claimed.attempts)


def _record_failed_attempt(
    claimed: repository.ClaimedNotification,
    error: Exception,
    engine: Engine,
    settings: Settings,
    clock: Callable[[], datetime],
    log_fields: dict[str, object],
) -> DeliveryOutcome:
    detail = _describe(error)
    now = clock()

    if claimed.attempts >= settings.notification_max_attempts:
        with engine.begin() as connection:
            repository.mark_failed(connection, claimed.id, error=detail, now=now)
        logger.error(
            "notification failed: attempts exhausted", extra={**log_fields, "error": detail}
        )
        return DeliveryOutcome(DeliveryResult.FAILED, claimed.attempts, detail=detail)

    delay = backoff_delay(
        claimed.attempts,
        base_seconds=settings.notification_retry_base_seconds,
        max_seconds=settings.notification_retry_max_seconds,
    )
    with engine.begin() as connection:
        repository.mark_retrying(
            connection, claimed.id, error=detail, next_attempt_at=now + delay, now=now
        )
    logger.warning(
        "notification attempt failed; retry scheduled",
        extra={**log_fields, "error": detail, "retry_in_seconds": delay.total_seconds()},
    )
    return DeliveryOutcome(
        DeliveryResult.RETRY_SCHEDULED, claimed.attempts, retry_delay=delay, detail=detail
    )
