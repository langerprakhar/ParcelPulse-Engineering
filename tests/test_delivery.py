"""Delivering a notification: exactly-once claims, retries and terminal failures."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import Engine

from parcelpulse_worker.config import Settings
from parcelpulse_worker.delivery import DeliveryOutcome, DeliveryResult, deliver_notification
from parcelpulse_worker.senders import (
    InMemoryEmailSender,
    PermanentDeliveryError,
    TransientDeliveryError,
)
from tests.conftest import NOW, FakeClock, create_notification, get_notification, make_settings


def deliver(
    notification_id: uuid.UUID,
    engine: Engine,
    sender: InMemoryEmailSender,
    settings: Settings,
    clock: FakeClock,
) -> DeliveryOutcome:
    return deliver_notification(
        notification_id, engine=engine, sender=sender, settings=settings, clock=clock
    )


def test_pending_notification_is_sent_and_recorded(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine, notification_type="OUT_FOR_DELIVERY")

    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome == DeliveryOutcome(DeliveryResult.SENT, attempts=1)
    (message,) = sender.sent
    assert message["To"] == "recipient@example.com"
    assert message["Subject"].startswith("Out for delivery: SC")
    assert message["X-ParcelPulse-Notification-Id"] == str(notification_id)

    row = get_notification(engine, notification_id)
    assert row.status == "SENT"
    assert row.attempts == 1
    assert row.sent_at == NOW
    assert row.claimed_at == NOW
    assert row.last_error is None
    assert row.next_attempt_at is None


def test_second_delivery_of_the_same_notification_sends_nothing(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    """A duplicated queue message must not become a duplicated email."""
    notification_id = create_notification(engine)

    first = deliver(notification_id, engine, sender, settings, clock)
    second = deliver(notification_id, engine, sender, settings, clock)
    third = deliver(notification_id, engine, sender, settings, clock)

    assert first.result is DeliveryResult.SENT
    assert second.result is DeliveryResult.SKIPPED
    assert third.result is DeliveryResult.SKIPPED
    assert len(sender.sent) == 1
    assert get_notification(engine, notification_id).attempts == 1


def test_concurrent_workers_send_a_notification_exactly_once(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    workers = 12

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(
            pool.map(
                lambda _: deliver(notification_id, engine, sender, settings, clock),
                range(workers),
            )
        )

    results = [outcome.result for outcome in outcomes]
    assert results.count(DeliveryResult.SENT) == 1
    assert results.count(DeliveryResult.SKIPPED) == workers - 1
    assert len(sender.sent) == 1
    assert get_notification(engine, notification_id).attempts == 1


@pytest.mark.parametrize("status", ["SENT", "FAILED", "SENDING"])
def test_notification_that_is_finished_or_in_flight_is_skipped(
    engine: Engine,
    sender: InMemoryEmailSender,
    settings: Settings,
    clock: FakeClock,
    status: str,
) -> None:
    notification_id = create_notification(engine, status=status, attempts=1)

    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome.result is DeliveryResult.SKIPPED
    assert outcome.detail == f"status={status}"
    assert sender.sent == []
    row = get_notification(engine, notification_id)
    assert (row.status, row.attempts) == (status, 1)


def test_unknown_notification_is_skipped(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    outcome = deliver(uuid.uuid4(), engine, sender, settings, clock)

    assert outcome.result is DeliveryResult.SKIPPED
    assert outcome.detail == "status=None"
    assert sender.sent == []


def test_transient_failure_schedules_a_retry_with_backoff(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError("mail server unavailable")]

    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome.result is DeliveryResult.RETRY_SCHEDULED
    assert outcome.attempts == 1
    assert outcome.retry_delay == timedelta(seconds=30)
    assert sender.sent == []

    row = get_notification(engine, notification_id)
    assert row.status == "RETRYING"
    assert row.attempts == 1
    assert row.next_attempt_at == NOW + timedelta(seconds=30)
    assert row.last_error == "TransientDeliveryError: mail server unavailable"
    assert row.sent_at is None


def test_retry_is_not_attempted_before_it_is_due(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError("mail server unavailable")]
    deliver(notification_id, engine, sender, settings, clock)

    clock.advance(seconds=29)
    early = deliver(notification_id, engine, sender, settings, clock)

    assert early.result is DeliveryResult.SKIPPED
    assert sender.sent == []
    assert get_notification(engine, notification_id).attempts == 1


def test_retry_succeeds_once_due_and_clears_the_error(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError("mail server unavailable")]
    deliver(notification_id, engine, sender, settings, clock)

    clock.advance(seconds=30)
    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome == DeliveryOutcome(DeliveryResult.SENT, attempts=2)
    assert len(sender.sent) == 1
    row = get_notification(engine, notification_id)
    assert row.status == "SENT"
    assert row.attempts == 2
    assert row.last_error is None
    assert row.next_attempt_at is None


def test_backoff_doubles_with_each_failed_attempt(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError("down") for _ in range(4)]

    delays = []
    for _ in range(4):
        outcome = deliver(notification_id, engine, sender, settings, clock)
        assert outcome.retry_delay is not None
        delays.append(outcome.retry_delay.total_seconds())
        clock.advance(seconds=outcome.retry_delay.total_seconds())

    assert delays == [30, 60, 120, 240]


def test_notification_fails_after_the_maximum_number_of_attempts(
    engine: Engine, sender: InMemoryEmailSender, database_url: str, clock: FakeClock
) -> None:
    settings = make_settings(database_url=database_url, notification_max_attempts=3)
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError(f"down {attempt}") for attempt in (1, 2, 3)]

    results = []
    for _ in range(3):
        outcome = deliver(notification_id, engine, sender, settings, clock)
        results.append(outcome.result)
        clock.advance(hours=2)

    assert results == [
        DeliveryResult.RETRY_SCHEDULED,
        DeliveryResult.RETRY_SCHEDULED,
        DeliveryResult.FAILED,
    ]
    row = get_notification(engine, notification_id)
    assert row.status == "FAILED"
    assert row.attempts == 3
    assert row.last_error == "TransientDeliveryError: down 3"
    assert row.next_attempt_at is None

    # FAILED is terminal: a later message for it does nothing.
    assert deliver(notification_id, engine, sender, settings, clock).result is (
        DeliveryResult.SKIPPED
    )
    assert sender.sent == []


def test_permanent_failure_is_not_retried(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [PermanentDeliveryError("recipient refused (SMTP 550)")]

    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome.result is DeliveryResult.FAILED
    assert outcome.retry_delay is None
    row = get_notification(engine, notification_id)
    assert row.status == "FAILED"
    assert row.attempts == 1
    assert row.last_error == "PermanentDeliveryError: recipient refused (SMTP 550)"


def test_unexpected_sender_error_is_treated_as_retryable(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [RuntimeError("bug in the transport")]

    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome.result is DeliveryResult.RETRY_SCHEDULED
    assert get_notification(engine, notification_id).last_error == (
        "RuntimeError: bug in the transport"
    )


def test_unsupported_channel_fails_permanently(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine, channel="SMS")

    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome.result is DeliveryResult.FAILED
    assert sender.sent == []
    assert "unsupported channel 'SMS'" in get_notification(engine, notification_id).last_error


def test_unsupported_notification_type_fails_permanently(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine, notification_type="RETURNED")

    outcome = deliver(notification_id, engine, sender, settings, clock)

    assert outcome.result is DeliveryResult.FAILED
    assert sender.sent == []


def test_very_long_error_is_truncated(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    notification_id = create_notification(engine)
    sender.failures = [TransientDeliveryError("x" * 5000)]

    deliver(notification_id, engine, sender, settings, clock)

    assert len(get_notification(engine, notification_id).last_error) == 1000


def test_worker_crash_during_send_leaves_the_notification_in_sending(
    engine: Engine, sender: InMemoryEmailSender, settings: Settings, clock: FakeClock
) -> None:
    """The claim is committed before the send, so a crash cannot cause a silent resend."""
    notification_id = create_notification(engine)
    sender.failures = [KeyboardInterrupt()]

    with pytest.raises(KeyboardInterrupt):
        deliver(notification_id, engine, sender, settings, clock)

    row = get_notification(engine, notification_id)
    assert (row.status, row.attempts) == ("SENDING", 1)
    # A redelivered queue message does not send while the first attempt is unresolved.
    assert deliver(notification_id, engine, sender, settings, clock).result is (
        DeliveryResult.SKIPPED
    )
    assert sender.sent == []
