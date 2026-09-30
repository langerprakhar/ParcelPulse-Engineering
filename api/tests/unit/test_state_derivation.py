"""The ordering policy: shipment state is a function of the event set, not arrival order."""

import itertools
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from parcelpulse_api.domain.state import EventFacts, arrived_out_of_order, derive_state
from parcelpulse_api.domain.status import (
    PROGRESS_RANK,
    STATUS_FOR_EVENT,
    EventType,
    ShipmentStatus,
)

T0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def hours(count: float) -> datetime:
    return T0 + timedelta(hours=count)


def event(
    event_type: EventType,
    event_at: datetime,
    *,
    received_at: datetime | None = None,
    eta: datetime | None = None,
) -> EventFacts:
    return EventFacts(
        id=uuid.uuid4(),
        event_type=event_type,
        event_at=event_at,
        received_at=received_at or event_at + timedelta(seconds=30),
        estimated_delivery_at=eta,
    )


LIFECYCLE = [
    (EventType.LABEL_CREATED, 0),
    (EventType.IN_TRANSIT, 4),
    (EventType.AT_DISTRIBUTION_CENTER, 20),
    (EventType.OUT_FOR_DELIVERY, 44),
    (EventType.DELIVERED, 50),
]


def test_every_event_type_maps_to_a_ranked_status() -> None:
    assert set(STATUS_FOR_EVENT) == set(EventType)
    assert set(PROGRESS_RANK) == set(ShipmentStatus)
    assert len(set(PROGRESS_RANK.values())) == len(PROGRESS_RANK)


def test_shipment_without_events_is_created() -> None:
    state = derive_state([])
    assert state.status is ShipmentStatus.CREATED
    assert state.last_event_at is None
    assert state.estimated_delivery_at is None
    assert state.deciding_event_id is None


def test_in_order_lifecycle_advances_through_each_status() -> None:
    events: list[EventFacts] = []
    for event_type, offset in LIFECYCLE:
        events.append(event(event_type, hours(offset)))
        state = derive_state(events)
        assert state.status is STATUS_FOR_EVENT[event_type]
        assert state.last_event_at == hours(offset)
        assert state.deciding_event_id == events[-1].id


def test_final_state_is_identical_for_every_arrival_order() -> None:
    events = [event(event_type, hours(offset)) for event_type, offset in LIFECYCLE]
    expected = derive_state(events)
    assert expected.status is ShipmentStatus.DELIVERED

    for arrival_order in itertools.permutations(events):
        assert derive_state(arrival_order) == expected


def test_late_historical_event_does_not_move_shipment_backwards() -> None:
    out_for_delivery = event(EventType.OUT_FOR_DELIVERY, hours(44))
    # A facility scan from the day before, delivered to us two days late.
    late_scan = event(EventType.AT_DISTRIBUTION_CENTER, hours(20), received_at=hours(70))

    state = derive_state([out_for_delivery, late_scan])

    assert state.status is ShipmentStatus.OUT_FOR_DELIVERY
    assert state.deciding_event_id == out_for_delivery.id
    assert state.last_event_at == hours(44)


def test_status_follows_carrier_time_even_when_received_first() -> None:
    # DELIVERED reaches us before the OUT_FOR_DELIVERY that preceded it.
    delivered = event(EventType.DELIVERED, hours(50), received_at=hours(50.1))
    out_for_delivery = event(EventType.OUT_FOR_DELIVERY, hours(44), received_at=hours(51))

    assert derive_state([delivered]).status is ShipmentStatus.DELIVERED
    assert derive_state([delivered, out_for_delivery]).status is ShipmentStatus.DELIVERED


def test_delivery_exception_is_recoverable() -> None:
    events = [
        event(EventType.OUT_FOR_DELIVERY, hours(44)),
        event(EventType.DELIVERY_EXCEPTION, hours(47)),
    ]
    assert derive_state(events).status is ShipmentStatus.DELIVERY_EXCEPTION

    events.append(event(EventType.OUT_FOR_DELIVERY, hours(68)))
    assert derive_state(events).status is ShipmentStatus.OUT_FOR_DELIVERY

    events.append(event(EventType.DELIVERED, hours(72)))
    assert derive_state(events).status is ShipmentStatus.DELIVERED


def test_stale_exception_arriving_after_redelivery_attempt_is_ignored_for_status() -> None:
    second_attempt = event(EventType.OUT_FOR_DELIVERY, hours(68))
    stale_exception = event(EventType.DELIVERY_EXCEPTION, hours(47), received_at=hours(69))

    assert derive_state([second_attempt, stale_exception]).status is (
        ShipmentStatus.OUT_FOR_DELIVERY
    )


@pytest.mark.parametrize("terminal", [EventType.DELIVERED, EventType.RETURNED])
@pytest.mark.parametrize(
    "later_scan",
    [
        EventType.IN_TRANSIT,
        EventType.AT_DISTRIBUTION_CENTER,
        EventType.OUT_FOR_DELIVERY,
        EventType.DELIVERY_EXCEPTION,
    ],
)
def test_terminal_status_is_sticky_against_later_dated_scans(
    terminal: EventType, later_scan: EventType
) -> None:
    terminal_event = event(terminal, hours(50))
    stray = event(later_scan, hours(55))

    state = derive_state([terminal_event, stray])

    assert state.status is STATUS_FOR_EVENT[terminal]
    assert state.deciding_event_id == terminal_event.id
    # The stray scan is still the most recent thing the carrier told us.
    assert state.last_event_at == hours(55)


def test_latest_terminal_event_wins_between_terminal_events() -> None:
    delivered = event(EventType.DELIVERED, hours(50))
    returned = event(EventType.RETURNED, hours(120))

    assert derive_state([returned, delivered]).status is ShipmentStatus.RETURNED
    assert derive_state([delivered, returned]).deciding_event_id == returned.id


def test_same_timestamp_is_broken_by_progression_rank() -> None:
    same_instant = hours(44)
    arrived = event(EventType.AT_DISTRIBUTION_CENTER, same_instant)
    out = event(EventType.OUT_FOR_DELIVERY, same_instant)

    assert derive_state([arrived, out]).status is ShipmentStatus.OUT_FOR_DELIVERY
    assert derive_state([out, arrived]).status is ShipmentStatus.OUT_FOR_DELIVERY


def test_same_timestamp_and_status_is_broken_by_receipt_time() -> None:
    first = event(EventType.IN_TRANSIT, hours(4), received_at=hours(5))
    second = event(EventType.IN_TRANSIT, hours(4), received_at=hours(6))

    assert derive_state([first, second]).deciding_event_id == second.id
    assert derive_state([second, first]).deciding_event_id == second.id


def test_estimate_comes_from_latest_event_that_carries_one() -> None:
    label = event(EventType.LABEL_CREATED, hours(0), eta=hours(48))
    transit = event(EventType.IN_TRANSIT, hours(4), eta=hours(52))
    # The newest event has no estimate: the previous one stays in force.
    hub = event(EventType.AT_DISTRIBUTION_CENTER, hours(20))

    assert derive_state([label]).estimated_delivery_at == hours(48)
    assert derive_state([label, transit]).estimated_delivery_at == hours(52)
    assert derive_state([label, transit, hub]).estimated_delivery_at == hours(52)


def test_late_historical_event_does_not_overwrite_newer_estimate() -> None:
    transit = event(EventType.IN_TRANSIT, hours(4), eta=hours(52))
    late_label = event(EventType.LABEL_CREATED, hours(0), received_at=hours(30), eta=hours(48))

    assert derive_state([transit, late_label]).estimated_delivery_at == hours(52)


def test_arrived_out_of_order_compares_carrier_time_only() -> None:
    known = [event(EventType.IN_TRANSIT, hours(4)), event(EventType.OUT_FOR_DELIVERY, hours(44))]

    assert arrived_out_of_order(event(EventType.AT_DISTRIBUTION_CENTER, hours(20)), known)
    assert not arrived_out_of_order(event(EventType.DELIVERED, hours(50)), known)
    assert not arrived_out_of_order(event(EventType.LABEL_CREATED, hours(0)), [])
