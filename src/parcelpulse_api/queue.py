"""Handing notifications to the worker.

The API never sends notifications itself. It writes a ``notifications`` row in
the webhook transaction and then publishes a small wake-up message naming that
row. The worker (parcelpulse-worker) declares the actor that consumes it.

The queue contract shared by both repositories:

* broker: Redis, through Dramatiq
* queue name: ``NOTIFICATION_QUEUE_NAME`` (default ``notifications``)
* actor name: ``NOTIFICATION_ACTOR_NAME`` (default ``deliver_notification``)
* args: ``[notification_id]`` as a string UUID
* kwargs: ``{"correlation_id": str | None}``

Publishing happens after commit and may fail without losing anything: the row
stays PENDING and the worker's sweeper picks it up.
"""

import logging
import uuid
from typing import Protocol

import dramatiq
import redis
from dramatiq.brokers.redis import RedisBroker

logger = logging.getLogger("parcelpulse.queue")


class NotificationPublisher(Protocol):
    def publish(self, notification_id: uuid.UUID, *, correlation_id: str | None = None) -> None:
        """Ask the worker to deliver a notification. Raises if the broker is unreachable."""

    def ping(self) -> None:
        """Raise if the broker is unreachable."""

    def close(self) -> None: ...


class DramatiqNotificationPublisher:
    def __init__(self, *, redis_url: str, queue_name: str, actor_name: str) -> None:
        self._queue_name = queue_name
        self._actor_name = actor_name
        self._client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=5)
        # No middleware: this process only enqueues, it never runs actors.
        self._broker = RedisBroker(client=self._client, middleware=[])  # type: ignore[no-untyped-call]

    def publish(self, notification_id: uuid.UUID, *, correlation_id: str | None = None) -> None:
        message: dramatiq.Message[None] = dramatiq.Message(
            queue_name=self._queue_name,
            actor_name=self._actor_name,
            args=(str(notification_id),),
            kwargs={"correlation_id": correlation_id},
            options={},
        )
        self._broker.enqueue(message)

    def ping(self) -> None:
        self._client.ping()

    def close(self) -> None:
        self._client.close()


class InMemoryNotificationPublisher:
    """Test double: records what would have been published."""

    def __init__(self) -> None:
        self.published: list[tuple[uuid.UUID, str | None]] = []
        self.fail_with: Exception | None = None

    def publish(self, notification_id: uuid.UUID, *, correlation_id: str | None = None) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.published.append((notification_id, correlation_id))

    def ping(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def close(self) -> None:
        return None
