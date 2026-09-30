"""Queue handling: the Dramatiq actor, driven through an in-memory broker and a real worker."""

import uuid
from typing import Any

import dramatiq
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from parcelpulse_worker import actors, runtime
from parcelpulse_worker.senders import InMemoryEmailSender, TransientDeliveryError
from tests.conftest import QUEUE, Harness, create_notification, get_notification, make_settings


def test_tests_use_the_in_memory_broker() -> None:
    assert type(actors.broker).__name__ == "StubBroker"


def test_actor_is_registered_under_the_contract_names() -> None:
    actor = actors.broker.get_actor("deliver_notification")
    assert actor.queue_name == QUEUE
    assert actor is actors.deliver_notification


def test_message_delivers_the_notification(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender
) -> None:
    notification_id = create_notification(engine)

    actors.deliver_notification.send(str(notification_id), correlation_id="corr-1")
    harness.drain()

    assert len(sender.sent) == 1
    assert get_notification(engine, notification_id).status == "SENT"


def test_message_published_the_way_the_api_publishes_is_consumed(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender
) -> None:
    """parcelpulse-api builds the message by hand, without importing this package."""
    notification_id = create_notification(engine)
    message: dramatiq.Message[Any] = dramatiq.Message(
        queue_name="notifications",
        actor_name="deliver_notification",
        args=(str(notification_id),),
        kwargs={"correlation_id": "corr-from-api"},
        options={},
    )

    actors.broker.enqueue(message)
    harness.drain()

    assert len(sender.sent) == 1
    assert get_notification(engine, notification_id).status == "SENT"


def test_duplicate_messages_result_in_one_email(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender
) -> None:
    notification_id = create_notification(engine)

    for _ in range(10):
        actors.deliver_notification.send(str(notification_id))
    harness.drain()

    assert len(sender.sent) == 1
    row = get_notification(engine, notification_id)
    assert (row.status, row.attempts) == ("SENT", 1)


def test_messages_for_different_notifications_are_all_delivered(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender
) -> None:
    notification_ids = [create_notification(engine) for _ in range(20)]

    for notification_id in notification_ids:
        actors.deliver_notification.send(str(notification_id))
    harness.drain()

    assert len(sender.sent) == 20
    delivered = {message["X-ParcelPulse-Notification-Id"] for message in sender.sent}
    assert delivered == {str(notification_id) for notification_id in notification_ids}


def test_failed_send_is_retried_through_a_delayed_message_until_it_succeeds(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError("down"), TransientDeliveryError("still down")]

    actors.deliver_notification.send(str(notification_id))
    harness.drain()

    assert len(sender.sent) == 1
    row = get_notification(engine, notification_id)
    assert (row.status, row.attempts) == ("SENT", 3)


def test_retries_stop_when_attempts_are_exhausted(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError("down") for _ in range(10)]

    actors.deliver_notification.send(str(notification_id))
    harness.drain()

    row = get_notification(engine, notification_id)
    assert (row.status, row.attempts) == ("FAILED", 3)
    assert sender.sent == []
    # Only the three allowed attempts consumed a scripted failure.
    assert len(sender.failures) == 7


def test_malformed_message_is_dropped_without_retrying(
    harness: Harness, sender: InMemoryEmailSender
) -> None:
    actors.deliver_notification.send("not-a-uuid")
    harness.drain()

    assert sender.sent == []
    assert actors.broker.dead_letters == []


def test_message_for_unknown_notification_is_acknowledged(
    harness: Harness, sender: InMemoryEmailSender
) -> None:
    actors.deliver_notification.send(str(uuid.uuid4()))
    harness.drain()

    assert sender.sent == []
    assert actors.broker.dead_letters == []


class FlakyEngine:
    """An engine whose first transactions fail, as if PostgreSQL were briefly unreachable."""

    def __init__(self, real: Engine, failures: int) -> None:
        self._real = real
        self.failures_left = failures

    def begin(self) -> Any:
        if self.failures_left > 0:
            self.failures_left -= 1
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        return self._real.begin()


def test_database_outage_before_the_claim_is_retried_by_the_queue(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender, database_url: str
) -> None:
    notification_id = create_notification(engine)
    flaky = FlakyEngine(engine, failures=1)
    runtime.set_runtime(
        runtime.Runtime(
            settings=make_settings(database_url=database_url),
            engine=flaky,  # type: ignore[arg-type]
            sender=sender,
        )
    )

    actors.deliver_notification.send(str(notification_id))
    harness.drain()

    assert flaky.failures_left == 0
    assert len(sender.sent) == 1
    row = get_notification(engine, notification_id)
    # The failed try never reached the claim, so it did not consume an attempt.
    assert (row.status, row.attempts) == ("SENT", 1)
