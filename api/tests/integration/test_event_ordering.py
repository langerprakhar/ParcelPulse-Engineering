"""Out-of-order and delayed carrier events, exercised through the HTTP API."""

import random
from datetime import datetime

from fastapi.testclient import TestClient

from tests.helpers import (
    carrier_event,
    get_shipment,
    get_timeline,
    hours,
    post_event,
    register_shipment,
)

LIFECYCLE = [
    ("LABEL_CREATED", 0),
    ("IN_TRANSIT", 4),
    ("AT_DISTRIBUTION_CENTER", 20),
    ("OUT_FOR_DELIVERY", 44),
    ("DELIVERED", 50),
]


def event_types(timeline: list[dict]) -> list[str]:
    return [entry["event_type"] for entry in timeline]


def test_delayed_historical_event_joins_the_timeline_without_moving_status_back(
    client: TestClient,
) -> None:
    shipment = register_shipment(client)
    post_event(client, carrier_event("IN_TRANSIT", hours(4)))
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))

    # A hub scan from the day before reaches us only now.
    late = post_event(client, carrier_event("AT_DISTRIBUTION_CENTER", hours(20))).json()

    assert late["result"] == "PROCESSED"
    assert late["shipment_status"] == "OUT_FOR_DELIVERY"

    current = get_shipment(client, shipment["id"])
    assert current["current_status"] == "OUT_FOR_DELIVERY"
    assert datetime.fromisoformat(current["last_event_at"]) == hours(44)

    timeline = get_timeline(client, shipment["id"])
    assert event_types(timeline) == ["IN_TRANSIT", "AT_DISTRIBUTION_CENTER", "OUT_FOR_DELIVERY"]
    late_entry = timeline[1]
    assert late_entry["arrived_out_of_order"] is True
    assert late_entry["changed_status"] is False
    assert late_entry["status_after"] == "OUT_FOR_DELIVERY"


def test_timeline_keeps_carrier_time_and_receipt_time_apart(client: TestClient) -> None:
    shipment = register_shipment(client)
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))
    post_event(client, carrier_event("AT_DISTRIBUTION_CENTER", hours(20)))

    hub, out = get_timeline(client, shipment["id"])

    # Chronological by carrier time...
    assert (hub["event_type"], out["event_type"]) == (
        "AT_DISTRIBUTION_CENTER",
        "OUT_FOR_DELIVERY",
    )
    assert hub["event_at"] < out["event_at"]
    # ...although the earlier event was received second.
    assert hub["received_at"] > out["received_at"]


def test_lifecycle_delivered_in_reverse_ends_delivered(client: TestClient) -> None:
    shipment = register_shipment(client)

    statuses_after_each_delivery = [
        post_event(client, carrier_event(event_type, hours(offset))).json()["shipment_status"]
        for event_type, offset in reversed(LIFECYCLE)
    ]

    # DELIVERED arrived first and nothing older could displace it.
    assert statuses_after_each_delivery == ["DELIVERED"] * len(LIFECYCLE)
    current = get_shipment(client, shipment["id"])
    assert current["current_status"] == "DELIVERED"
    assert datetime.fromisoformat(current["last_event_at"]) == hours(50)

    timeline = get_timeline(client, shipment["id"])
    assert event_types(timeline) == [event_type for event_type, _ in LIFECYCLE]
    assert [entry["arrived_out_of_order"] for entry in timeline] == [True, True, True, True, False]
    assert [entry["changed_status"] for entry in timeline] == [False, False, False, False, True]


def test_lifecycle_delivered_in_shuffled_order_matches_in_order_result(
    client: TestClient,
) -> None:
    in_order = register_shipment(client, "SCORDERED001")
    for event_type, offset in LIFECYCLE:
        post_event(client, carrier_event(event_type, hours(offset), tracking_number="SCORDERED001"))

    shuffled = register_shipment(client, "SCSHUFFLED01")
    arrival = LIFECYCLE.copy()
    random.Random(20260930).shuffle(arrival)
    assert arrival != LIFECYCLE
    for event_type, offset in arrival:
        post_event(client, carrier_event(event_type, hours(offset), tracking_number="SCSHUFFLED01"))

    expected = get_shipment(client, in_order["id"])
    actual = get_shipment(client, shuffled["id"])
    for field in ("current_status", "last_event_at", "estimated_delivery_at"):
        assert actual[field] == expected[field]
    assert event_types(get_timeline(client, shuffled["id"])) == event_types(
        get_timeline(client, in_order["id"])
    )


def test_status_follows_carrier_time_when_events_arrive_swapped(client: TestClient) -> None:
    shipment = register_shipment(client)

    first = post_event(client, carrier_event("AT_DISTRIBUTION_CENTER", hours(20))).json()
    second = post_event(client, carrier_event("IN_TRANSIT", hours(4))).json()

    assert first["shipment_status"] == "AT_DISTRIBUTION_CENTER"
    assert second["shipment_status"] == "AT_DISTRIBUTION_CENTER"
    assert get_shipment(client, shipment["id"])["current_status"] == "AT_DISTRIBUTION_CENTER"


def test_late_event_after_delivery_does_not_reopen_the_shipment(client: TestClient) -> None:
    shipment = register_shipment(client)
    post_event(client, carrier_event("DELIVERED", hours(50)))

    post_event(client, carrier_event("DELIVERY_EXCEPTION", hours(47)))
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))

    assert get_shipment(client, shipment["id"])["current_status"] == "DELIVERED"
    assert event_types(get_timeline(client, shipment["id"])) == [
        "OUT_FOR_DELIVERY",
        "DELIVERY_EXCEPTION",
        "DELIVERED",
    ]


def test_stray_scan_dated_after_delivery_is_recorded_but_delivery_stands(
    client: TestClient,
) -> None:
    shipment = register_shipment(client)
    post_event(client, carrier_event("DELIVERED", hours(50)))

    stray = post_event(client, carrier_event("IN_TRANSIT", hours(55))).json()

    assert stray["result"] == "PROCESSED"
    assert stray["shipment_status"] == "DELIVERED"
    current = get_shipment(client, shipment["id"])
    assert current["current_status"] == "DELIVERED"
    assert datetime.fromisoformat(current["last_event_at"]) == hours(55)
    assert event_types(get_timeline(client, shipment["id"])) == ["DELIVERED", "IN_TRANSIT"]


def test_delivery_exception_then_second_attempt_then_delivery(client: TestClient) -> None:
    shipment = register_shipment(client)
    sequence = [
        ("OUT_FOR_DELIVERY", 44, "OUT_FOR_DELIVERY"),
        ("DELIVERY_EXCEPTION", 47, "DELIVERY_EXCEPTION"),
        ("OUT_FOR_DELIVERY", 68, "OUT_FOR_DELIVERY"),
        ("DELIVERED", 72, "DELIVERED"),
    ]
    for event_type, offset, expected_status in sequence:
        post_event(client, carrier_event(event_type, hours(offset)))
        assert get_shipment(client, shipment["id"])["current_status"] == expected_status


def test_late_event_does_not_overwrite_a_newer_delivery_estimate(client: TestClient) -> None:
    shipment = register_shipment(client)
    post_event(
        client,
        carrier_event("IN_TRANSIT", hours(4), estimated_delivery_at=hours(52).isoformat()),
    )

    # The label event, with the carrier's original and now outdated estimate, arrives late.
    post_event(
        client,
        carrier_event("LABEL_CREATED", hours(0), estimated_delivery_at=hours(48).isoformat()),
    )

    current = get_shipment(client, shipment["id"])
    assert datetime.fromisoformat(current["estimated_delivery_at"]) == hours(52)


def test_estimate_is_kept_when_newer_events_carry_none(client: TestClient) -> None:
    shipment = register_shipment(client)
    post_event(
        client,
        carrier_event("IN_TRANSIT", hours(4), estimated_delivery_at=hours(52).isoformat()),
    )
    post_event(client, carrier_event("AT_DISTRIBUTION_CENTER", hours(20)))

    current = get_shipment(client, shipment["id"])
    assert current["current_status"] == "AT_DISTRIBUTION_CENTER"
    assert datetime.fromisoformat(current["estimated_delivery_at"]) == hours(52)
