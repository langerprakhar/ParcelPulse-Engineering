"""Dramatiq broker and actors. This is the module the worker process loads::

    dramatiq parcelpulse_worker.actors

Queue contract with parcelpulse-api (which publishes without importing this code):

* queue ``NOTIFICATION_QUEUE_NAME`` (default ``notifications``)
* actor ``NOTIFICATION_ACTOR_NAME`` (default ``deliver_notification``)
* args ``[notification_id]`` (string UUID), kwargs ``{"correlation_id": str | None}``

A message is only a wake-up call: all state lives in the ``notifications``
table, so lost, duplicated or reordered messages cannot cause a lost or
duplicated notification.
"""

import logging
import uuid

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

from parcelpulse_worker import delivery
from parcelpulse_worker.config import Settings, get_settings
from parcelpulse_worker.delivery import DeliveryResult
from parcelpulse_worker.logging_config import configure_logging, correlation_scope
from parcelpulse_worker.runtime import get_runtime

logger = logging.getLogger("parcelpulse.worker.actors")

# Added to the retry delay so the delayed message cannot arrive a moment before
# the row's next_attempt_at, e.g. with slightly different clocks between hosts.
RETRY_MARGIN_MS = 250


def build_broker(settings: Settings) -> dramatiq.Broker:
    if settings.queue_broker == "stub":
        return StubBroker()
    return RedisBroker(url=settings.redis_url)  # type: ignore[no-untyped-call]


_settings = get_settings()
configure_logging(
    service=_settings.service_name, level=_settings.log_level, log_format=_settings.log_format
)
broker = build_broker(_settings)
dramatiq.set_broker(broker)


# max_retries covers *unexpected* errors (for example the database being
# unreachable before the claim). Failed sends are retried through the
# notification row's own attempt counter, not through Dramatiq.
@dramatiq.actor(
    actor_name=_settings.notification_actor_name,
    queue_name=_settings.notification_queue_name,
    max_retries=3,
    min_backoff=1_000,
    max_backoff=30_000,
)
def deliver_notification(notification_id: str, correlation_id: str | None = None) -> None:
    with correlation_scope(correlation_id):
        try:
            parsed_id = uuid.UUID(notification_id)
        except (ValueError, AttributeError, TypeError):
            # Retrying cannot fix a malformed message; drop it.
            logger.error("dropping message with malformed notification id")
            return

        runtime = get_runtime()
        outcome = delivery.deliver_notification(
            parsed_id, engine=runtime.engine, sender=runtime.sender, settings=runtime.settings
        )

        if outcome.result is DeliveryResult.RETRY_SCHEDULED and outcome.retry_delay is not None:
            delay_ms = int(outcome.retry_delay.total_seconds() * 1000) + RETRY_MARGIN_MS
            deliver_notification.send_with_options(
                args=(notification_id,),
                kwargs={"correlation_id": correlation_id},
                delay=delay_ms,
            )
