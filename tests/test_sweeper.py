"""The sweeper: recovering notifications whose message was lost or whose worker died."""

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import Engine

from parcelpulse_worker import actors, runtime, sweeper
from parcelpulse_worker.config import Settings
from parcelpulse_worker.delivery import DeliveryResult, deliver_notification
from parcelpulse_worker.senders import InMemoryEmailSender
from parcelpulse_worker.sweeper import ABANDONED_ERROR, SweepResult, sweep_once
from tests.conftest import (
    NOW,
    FakeClock,
    Harness,
    create_notification,
    get_notification,
    make_settings,
)


class Published:
    """Collects what the sweeper asks to have queued."""

    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, str | None]] = []
        self.fail = False

    def __call__(self, notification_id: uuid.UUID, correlation_id: str | None) -> None:
        if self.fail:
            raise ConnectionError("broker unavailable")
        self.calls.append((notification_id, correlation_id))

    @property
    def ids(self) -> list[uuid.UUID]:
        return [notification_id for notification_id, _ in self.calls]


def test_pending_notification_older_than_the_grace_period_is_republished(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    """The API committed the row but its publish never reached the queue."""
    lost = create_notification(engine, created_at=NOW - timedelta(seconds=31))
    fresh = create_notification(engine, created_at=NOW - timedelta(seconds=5))
    published = Published()

    result = sweep_once(engine, published, settings, clock)

    assert published.ids == [lost]
    assert result == SweepResult(requeued=1)
    assert get_notification(engine, lost).status == "PENDING"
    assert get_notification(engine, fresh).updated_at == NOW - timedelta(seconds=5)


def test_correlation_id_is_passed_on_when_republishing(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    lost = create_notification(
        engine, created_at=NOW - timedelta(minutes=5), correlation_id="carrier-delivery-7"
    )
    published = Published()

    sweep_once(engine, published, settings, clock)

    assert published.calls == [(lost, "carrier-delivery-7")]


def test_a_row_is_republished_at_most_once_per_grace_period(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    create_notification(engine, created_at=NOW - timedelta(minutes=5))
    published = Published()

    sweep_once(engine, published, settings, clock)
    clock.advance(seconds=15)
    sweep_once(engine, published, settings, clock)
    assert len(published.calls) == 1

    clock.advance(seconds=15)
    sweep_once(engine, published, settings, clock)
    assert len(published.calls) == 2


def test_overdue_retry_is_republished_but_a_scheduled_one_is_left_alone(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    long_ago = NOW - timedelta(minutes=10)
    overdue = create_notification(
        engine,
        status="RETRYING",
        attempts=1,
        created_at=long_ago,
        next_attempt_at=NOW - timedelta(seconds=31),
    )
    create_notification(  # due, but its delayed message is probably still on its way
        engine,
        status="RETRYING",
        attempts=1,
        created_at=long_ago,
        next_attempt_at=NOW - timedelta(seconds=5),
    )
    create_notification(  # not due yet
        engine,
        status="RETRYING",
        attempts=1,
        created_at=long_ago,
        next_attempt_at=NOW + timedelta(minutes=5),
    )
    published = Published()

    sweep_once(engine, published, settings, clock)

    assert published.ids == [overdue]


def test_finished_notifications_are_never_republished(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    for status in ("SENT", "FAILED"):
        create_notification(engine, status=status, attempts=1, created_at=NOW - timedelta(days=1))
    published = Published()

    assert sweep_once(engine, published, settings, clock) == SweepResult()
    assert published.calls == []


def test_batch_size_limits_a_sweep_and_the_oldest_go_first(
    engine: Engine, database_url: str, clock: FakeClock
) -> None:
    settings = make_settings(database_url=database_url, sweep_batch_size=2)
    oldest = create_notification(engine, created_at=NOW - timedelta(minutes=30))
    newest = create_notification(engine, created_at=NOW - timedelta(minutes=10))
    middle = create_notification(engine, created_at=NOW - timedelta(minutes=20))
    published = Published()

    sweep_once(engine, published, settings, clock)
    assert set(published.ids) == {oldest, middle}

    sweep_once(engine, published, settings, clock)
    assert published.ids[2:] == [newest]


def test_abandoned_send_is_released_and_queued_again(
    engine: Engine, settings: Settings, clock: FakeClock, sender: InMemoryEmailSender
) -> None:
    """A worker claimed the notification and died before recording the result."""
    abandoned = create_notification(
        engine, status="SENDING", attempts=1, claimed_at=NOW - timedelta(seconds=121)
    )
    published = Published()

    result = sweep_once(engine, published, settings, clock)

    assert result == SweepResult(released=1, requeued=1)
    assert published.ids == [abandoned]
    row = get_notification(engine, abandoned)
    assert row.status == "RETRYING"
    assert row.next_attempt_at == NOW
    assert row.last_error == ABANDONED_ERROR

    # The queued message now leads to a second, recorded attempt.
    outcome = deliver_notification(
        abandoned, engine=engine, sender=sender, settings=settings, clock=clock
    )
    assert outcome.result is DeliveryResult.SENT
    assert get_notification(engine, abandoned).attempts == 2


def test_send_within_its_lease_is_not_touched(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    in_flight = create_notification(
        engine, status="SENDING", attempts=1, claimed_at=NOW - timedelta(seconds=60)
    )
    published = Published()

    assert sweep_once(engine, published, settings, clock) == SweepResult()
    assert get_notification(engine, in_flight).status == "SENDING"


def test_abandoned_send_with_no_attempts_left_is_failed_not_requeued(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    exhausted = create_notification(
        engine,
        status="SENDING",
        attempts=settings.notification_max_attempts,
        claimed_at=NOW - timedelta(minutes=10),
    )
    published = Published()

    result = sweep_once(engine, published, settings, clock)

    assert result == SweepResult(abandoned=1)
    assert published.calls == []
    row = get_notification(engine, exhausted)
    assert row.status == "FAILED"
    assert row.next_attempt_at is None
    assert row.last_error == ABANDONED_ERROR


def test_broker_outage_during_a_sweep_is_counted_and_retried_later(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    lost = create_notification(engine, created_at=NOW - timedelta(minutes=5))
    published = Published()
    published.fail = True

    result = sweep_once(engine, published, settings, clock)
    assert result == SweepResult(publish_errors=1)
    assert get_notification(engine, lost).status == "PENDING"

    published.fail = False
    clock.advance(seconds=30)
    assert sweep_once(engine, published, settings, clock) == SweepResult(requeued=1)
    assert published.ids == [lost]


def test_concurrent_sweepers_do_not_republish_the_same_row_twice(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    for _ in range(20):
        create_notification(engine, created_at=NOW - timedelta(minutes=5))
    published = Published()
    barrier = threading.Barrier(4)

    def sweep() -> None:
        barrier.wait()
        sweep_once(engine, published, settings, clock)

    threads = [threading.Thread(target=sweep) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(published.ids) == 20
    assert len(set(published.ids)) == 20


def test_lost_message_is_recovered_end_to_end(
    harness: Harness, engine: Engine, sender: InMemoryEmailSender, settings: Settings
) -> None:
    """No message was ever published; the sweeper and a real worker still deliver it."""
    lost = create_notification(engine, created_at=NOW - timedelta(days=1))

    def enqueue(notification_id: uuid.UUID, correlation_id: str | None) -> None:
        actors.deliver_notification.send(str(notification_id), correlation_id=correlation_id)

    result = sweep_once(engine, enqueue, settings)
    harness.drain()

    assert result == SweepResult(requeued=1)
    assert len(sender.sent) == 1
    assert get_notification(engine, lost).status == "SENT"


def test_run_loop_sweeps_until_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = threading.Event()
    sweeps: list[int] = []

    def fake_sweep(*args: object, **kwargs: object) -> SweepResult:
        sweeps.append(1)
        if len(sweeps) == 1:
            raise RuntimeError("database briefly unavailable")
        stop.set()
        return SweepResult()

    monkeypatch.setattr(sweeper, "sweep_once", fake_sweep)
    monkeypatch.setattr(sweeper, "get_settings", lambda: make_settings(sweep_interval_seconds=0.01))

    try:
        sweeper.run(stop)
    finally:
        runtime.set_runtime(None)

    # The first sweep failed; the loop survived and swept again.
    assert len(sweeps) == 2
