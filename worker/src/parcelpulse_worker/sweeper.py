"""The sweeper: a safety net for notifications the queue alone would lose.

Run as its own process::

    python -m parcelpulse_worker.sweeper

Every ``SWEEP_INTERVAL_SECONDS`` it does two things:

1. **Releases abandoned claims.** A row that has been SENDING for longer than
   ``SENDING_LEASE_SECONDS`` belongs to a worker that died mid-send. It goes
   back to RETRYING (or to FAILED if its attempts are used up) and is queued
   again. Because the send may already have happened, this is the one path on
   which a notification can be delivered twice.
2. **Re-publishes overdue rows.** PENDING rows and due RETRYING rows that
   nobody has picked up within ``SWEEP_GRACE_SECONDS`` get a fresh queue
   message. This covers the API committing a notification but failing to
   publish it, and messages lost with a Redis restart.

Re-publishing is always safe: the worker's claim decides whether a message
leads to a send. Each re-publish touches ``updated_at``, which limits it to once
per grace period per row, including when several sweepers run.
"""

import logging
import signal
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import FrameType

from sqlalchemy import Engine, and_, case, or_, select, update

from parcelpulse_worker.config import Settings, get_settings
from parcelpulse_worker.db import FAILED, PENDING, RETRYING, SENDING, notifications
from parcelpulse_worker.delivery import utcnow
from parcelpulse_worker.logging_config import configure_logging, correlation_scope

logger = logging.getLogger("parcelpulse.worker.sweeper")

ABANDONED_ERROR = "send not confirmed: the worker stopped while SENDING (lease expired)"

Enqueue = Callable[[uuid.UUID, str | None], None]


@dataclass(frozen=True, slots=True)
class SweepResult:
    # Stale SENDING rows returned to RETRYING.
    released: int = 0
    # Stale SENDING rows marked FAILED because their attempts were used up.
    abandoned: int = 0
    # Queue messages published.
    requeued: int = 0
    # Rows that should have been published but the broker refused.
    publish_errors: int = 0


def sweep_once(
    engine: Engine,
    enqueue: Enqueue,
    settings: Settings,
    clock: Callable[[], datetime] = utcnow,
) -> SweepResult:
    now = clock()
    lease = timedelta(seconds=settings.sending_lease_seconds)
    grace = timedelta(seconds=settings.sweep_grace_seconds)
    exhausted = notifications.c.attempts >= settings.notification_max_attempts

    with engine.begin() as connection:
        stale = connection.execute(
            update(notifications)
            .where(notifications.c.status == SENDING, notifications.c.claimed_at < now - lease)
            .values(
                status=case((exhausted, FAILED), else_=RETRYING),
                next_attempt_at=case((exhausted, None), else_=now),
                last_error=ABANDONED_ERROR,
                updated_at=now,
            )
            .returning(notifications.c.id, notifications.c.status, notifications.c.correlation_id)
        ).all()

        overdue = (
            select(notifications.c.id)
            .where(
                notifications.c.updated_at <= now - grace,
                or_(
                    notifications.c.status == PENDING,
                    and_(
                        notifications.c.status == RETRYING,
                        notifications.c.next_attempt_at <= now - grace,
                    ),
                ),
            )
            .order_by(notifications.c.created_at)
            .limit(settings.sweep_batch_size)
            # Two sweepers running at once pick disjoint batches.
            .with_for_update(skip_locked=True)
        )
        touched = connection.execute(
            update(notifications)
            .where(notifications.c.id.in_(overdue))
            .values(updated_at=now)
            .returning(notifications.c.id, notifications.c.correlation_id)
        ).all()

    released = [row for row in stale if row.status == RETRYING]
    to_publish = [(row.id, row.correlation_id) for row in (*released, *touched)]

    requeued = publish_errors = 0
    for notification_id, correlation_id in to_publish:
        with correlation_scope(correlation_id):
            try:
                enqueue(notification_id, correlation_id)
                requeued += 1
            except Exception:
                publish_errors += 1
                logger.exception(
                    "sweeper could not publish notification",
                    extra={"notification_id": str(notification_id)},
                )

    result = SweepResult(
        released=len(released),
        abandoned=len(stale) - len(released),
        requeued=requeued,
        publish_errors=publish_errors,
    )
    if result != SweepResult():
        logger.info(
            "sweep finished",
            extra={
                "released": result.released,
                "abandoned": result.abandoned,
                "requeued": result.requeued,
                "publish_errors": result.publish_errors,
            },
        )
    return result


def run(stop: threading.Event | None = None) -> None:
    """Sweep forever (or until ``stop`` is set)."""
    # Imported here: loading the actors module builds the broker connection.
    from parcelpulse_worker import actors
    from parcelpulse_worker.runtime import get_runtime

    settings = get_settings()
    configure_logging(
        service=f"{settings.service_name}-sweeper",
        level=settings.log_level,
        log_format=settings.log_format,
    )
    runtime = get_runtime()
    stop = stop or threading.Event()

    def enqueue(notification_id: uuid.UUID, correlation_id: str | None) -> None:
        actors.deliver_notification.send(str(notification_id), correlation_id=correlation_id)

    logger.info("sweeper started", extra={"interval_seconds": settings.sweep_interval_seconds})
    while not stop.is_set():
        try:
            sweep_once(runtime.engine, enqueue, settings)
        except Exception:
            # Usually the database being unavailable; try again on the next tick.
            logger.exception("sweep failed")
        stop.wait(settings.sweep_interval_seconds)
    logger.info("sweeper stopped")


def main() -> None:
    stop = threading.Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run(stop)


if __name__ == "__main__":
    main()
