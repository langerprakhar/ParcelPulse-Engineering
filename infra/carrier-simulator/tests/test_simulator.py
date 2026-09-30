"""The simulated carrier's behaviours: ordered, duplicate, delayed and out-of-order events."""

from datetime import datetime, timedelta

import pytest

from carrier_simulator.scenarios import SCENARIOS
from carrier_simulator.simulator import (
    RegistrationError,
    Simulator,
    SimulatorError,
    UnknownShipmentError,
)
from tests.conftest import NOW, FakeParcelPulse

STANDARD = [step.event_type for step in SCENARIOS["standard"]]


def occurred_at(receiver: FakeParcelPulse) -> list[datetime]:
    return [datetime.fromisoformat(webhook.payload["occurred_at"]) for webhook in receiver.webhooks]


def test_new_shipment_has_a_planned_journey_entirely_in_the_past(simulator: Simulator) -> None:
    shipment = simulator.create_shipment()

    assert shipment.tracking_number.startswith("SC")
    assert len(shipment.tracking_number) == 12
    assert [event.step.event_type for event in shipment.events] == STANDARD
    times = [event.occurred_at for event in shipment.events]
    assert times == sorted(times)
    # The receiver rejects events dated in the future, so the journey must already be over.
    assert times[-1] == NOW - timedelta(hours=2)
    assert all(event.state == "planned" for event in shipment.events)


def test_creating_a_shipment_sends_nothing(simulator: Simulator, receiver: FakeParcelPulse) -> None:
    simulator.create_shipment()
    assert receiver.webhooks == []


def test_tracking_number_can_be_chosen_and_must_be_unique(simulator: Simulator) -> None:
    simulator.create_shipment(tracking_number="sc4f7k2m9q1x")

    assert simulator.get("SC4F7K2M9Q1X").tracking_number == "SC4F7K2M9Q1X"
    with pytest.raises(SimulatorError, match="already exists"):
        simulator.create_shipment(tracking_number="SC4F7K2M9Q1X")


def test_unknown_scenario_and_unknown_shipment_are_errors(simulator: Simulator) -> None:
    with pytest.raises(SimulatorError, match="unknown scenario"):
        simulator.create_shipment(scenario="teleport")
    with pytest.raises(UnknownShipmentError):
        simulator.get("SCNOBODY0001")


def test_advance_sends_events_in_journey_order(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()

    first = simulator.advance(shipment.tracking_number)
    rest = simulator.advance(shipment.tracking_number, count=2)

    assert [delivery.event_type for delivery in (*first, *rest)] == STANDARD[:3]
    assert receiver.event_types == STANDARD[:3]
    assert all(delivery.send.delivered and not delivery.duplicate for delivery in (*first, *rest))
    assert [event.state for event in shipment.events][:4] == ["sent", "sent", "sent", "planned"]


def test_webhook_payload_follows_the_carrier_contract(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment(tracking_number="SC4F7K2M9Q1X")

    simulator.advance(shipment.tracking_number)

    payload = receiver.webhooks[0].payload
    assert payload == {
        "provider": "simcarrier",
        "event_id": shipment.events[0].event_id,
        "tracking_number": "SC4F7K2M9Q1X",
        "event_type": "LABEL_CREATED",
        "occurred_at": shipment.events[0].occurred_at.isoformat(),
        "location": {
            "facility": "Leeds Parcel Hub",
            "city": "Leeds",
            "region": "ENG",
            "country": "GB",
        },
        "description": "Shipping label created",
        "estimated_delivery_at": (shipment.started_at + timedelta(hours=52)).isoformat(),
    }
    assert datetime.fromisoformat(payload["occurred_at"]).tzinfo is not None


def test_advancing_a_finished_journey_is_an_error(simulator: Simulator) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=len(STANDARD))

    with pytest.raises(SimulatorError, match="journey is complete"):
        simulator.advance(shipment.tracking_number)


def test_duplicate_resends_the_last_event_byte_for_byte(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=2)

    duplicates = simulator.duplicate(shipment.tracking_number, count=3)

    assert [delivery.duplicate for delivery in duplicates] == [True, True, True]
    assert [delivery.send.result for delivery in duplicates] == ["DUPLICATE"] * 3
    original, *repeats = receiver.webhooks[1:]
    assert all(repeat.body == original.body for repeat in repeats)
    assert {webhook.payload["event_id"] for webhook in receiver.webhooks[1:]} == {
        shipment.events[1].event_id
    }


def test_duplicate_can_target_an_earlier_event(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=3)

    simulator.duplicate(shipment.tracking_number, event_id=shipment.events[0].event_id)

    assert receiver.webhooks[-1].payload["event_type"] == "LABEL_CREATED"
    assert receiver.webhooks[-1].body == receiver.webhooks[0].body


def test_duplicate_requires_an_event_that_was_sent(simulator: Simulator) -> None:
    shipment = simulator.create_shipment()

    with pytest.raises(SimulatorError, match="no event has been sent"):
        simulator.duplicate(shipment.tracking_number)

    simulator.advance(shipment.tracking_number)
    with pytest.raises(SimulatorError, match="has not been sent"):
        simulator.duplicate(shipment.tracking_number, event_id=shipment.events[3].event_id)


def test_held_event_is_delivered_late_with_its_original_time(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=2)

    held = simulator.hold(shipment.tracking_number)
    simulator.advance(shipment.tracking_number, count=2)
    released = simulator.release_held(shipment.tracking_number)

    assert [event.step.event_type for event in held] == ["AT_DISTRIBUTION_CENTER"]
    assert receiver.event_types == [
        "LABEL_CREATED",
        "IN_TRANSIT",
        "IN_TRANSIT",
        "AT_DISTRIBUTION_CENTER",
        "AT_DISTRIBUTION_CENTER",
    ]
    times = occurred_at(receiver)
    # The last webhook carries an event time earlier than the two sent before it.
    assert times[4] < times[2] < times[3]
    assert released[0].event_id == held[0].event_id
    assert released[0].duplicate is False


def test_release_without_held_events_is_an_error(simulator: Simulator) -> None:
    shipment = simulator.create_shipment()
    with pytest.raises(SimulatorError, match="no held events"):
        simulator.release_held(shipment.tracking_number)


def test_out_of_order_swaps_the_next_two_events(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()

    simulator.out_of_order(shipment.tracking_number)

    assert receiver.event_types == ["IN_TRANSIT", "LABEL_CREATED"]
    first_sent, second_sent = occurred_at(receiver)
    assert second_sent < first_sent


def test_out_of_order_needs_two_planned_events(simulator: Simulator) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=len(STANDARD) - 1)

    with pytest.raises(SimulatorError, match="at least two"):
        simulator.out_of_order(shipment.tracking_number)


def test_injected_exception_falls_between_the_surrounding_events(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=6)  # up to OUT_FOR_DELIVERY

    (delivery,) = simulator.exception(shipment.tracking_number)

    assert delivery.event_type == "DELIVERY_EXCEPTION"
    out_for_delivery = shipment.events[5].occurred_at
    delivered = next(e for e in shipment.events if e.step.event_type == "DELIVERED").occurred_at
    assert out_for_delivery < delivery.occurred_at < delivered
    assert receiver.event_types[-1] == "DELIVERY_EXCEPTION"
    # The journey can still be completed afterwards.
    assert simulator.advance(shipment.tracking_number)[0].event_type == "DELIVERED"


def test_exception_after_the_final_event_is_still_in_the_past(simulator: Simulator) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=len(STANDARD))

    (delivery,) = simulator.exception(shipment.tracking_number)

    assert shipment.events[-2].occurred_at < delivery.occurred_at < NOW


def test_exception_needs_a_sent_event(simulator: Simulator) -> None:
    shipment = simulator.create_shipment()
    with pytest.raises(SimulatorError, match="at least one event"):
        simulator.exception(shipment.tracking_number)


def test_lifecycle_sends_everything_that_is_left(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()
    simulator.advance(shipment.tracking_number, count=2)
    simulator.hold(shipment.tracking_number)

    deliveries = simulator.lifecycle(shipment.tracking_number)

    assert [delivery.event_type for delivery in deliveries] == STANDARD[2:]
    assert all(event.state == "sent" for event in shipment.events)
    with pytest.raises(SimulatorError, match="already been sent"):
        simulator.lifecycle(shipment.tracking_number)


def test_shuffled_lifecycle_sends_every_event_once_in_a_different_order(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()

    simulator.lifecycle(shipment.tracking_number, shuffle=True)

    assert sorted(receiver.event_types) == sorted(STANDARD)
    assert receiver.event_types != STANDARD
    assert len({webhook.payload["event_id"] for webhook in receiver.webhooks}) == len(STANDARD)


def test_lifecycle_with_duplicates_repeats_each_event(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()

    deliveries = simulator.lifecycle(shipment.tracking_number, duplicates=2)

    assert len(deliveries) == len(STANDARD) * 3
    assert [delivery.duplicate for delivery in deliveries[:3]] == [False, True, True]
    results = [delivery.send.result for delivery in deliveries]
    assert results.count("PROCESSED") == len(STANDARD)
    assert results.count("DUPLICATE") == len(STANDARD) * 2


@pytest.mark.parametrize(
    ("scenario", "ending"),
    [
        ("standard", ["OUT_FOR_DELIVERY", "DELIVERED"]),
        ("exception", ["DELIVERY_EXCEPTION", "OUT_FOR_DELIVERY", "DELIVERED"]),
        ("returned", ["DELIVERY_EXCEPTION", "RETURNED"]),
    ],
)
def test_scenarios_end_as_described(
    simulator: Simulator, receiver: FakeParcelPulse, scenario: str, ending: list[str]
) -> None:
    shipment = simulator.create_shipment(scenario=scenario)

    simulator.lifecycle(shipment.tracking_number)

    assert receiver.event_types[-len(ending) :] == ending
    times = occurred_at(receiver)
    assert times == sorted(times)
    assert times[-1] <= NOW


def test_registration_tells_parcelpulse_about_the_shipment(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment(register=True, notification_email="dev@example.com")

    assert shipment.registered is True
    assert receiver.registrations == [
        {
            "tracking_number": shipment.tracking_number,
            "carrier": "simcarrier",
            "notification_email": "dev@example.com",
        }
    ]


def test_registration_is_skipped_unless_requested(
    simulator: Simulator, receiver: FakeParcelPulse
) -> None:
    shipment = simulator.create_shipment()
    assert shipment.registered is False
    assert receiver.registrations == []


def test_registration_without_a_configured_api_is_an_error(sender: object) -> None:
    unconfigured = Simulator(sender)  # type: ignore[arg-type]
    with pytest.raises(RegistrationError, match="not configured"):
        unconfigured.create_shipment(register=True)


def test_burst_plays_out_many_journeys(simulator: Simulator, receiver: FakeParcelPulse) -> None:
    summary = simulator.burst(shipments=12, shuffle=True, duplicates=1, concurrency=6)

    events = 12 * len(STANDARD)
    assert summary.shipments == 12
    assert summary.events == events
    assert summary.deliveries == events * 2
    assert summary.http_attempts == events * 2
    assert summary.undelivered == 0
    assert summary.results == {"PROCESSED": events, "DUPLICATE": events}
    assert len(set(summary.tracking_numbers)) == 12
    assert len(receiver.registrations) == 12
    assert len(receiver.webhooks) == events * 2
