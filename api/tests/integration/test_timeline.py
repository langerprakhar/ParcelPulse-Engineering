"""GET /shipments/{id}/events: the historical timeline."""

import uuid

from fastapi.testclient import TestClient

from tests.helpers import carrier_event, get_timeline, hours, post_event, register_shipment


def seed_timeline(client: TestClient, tracking_number: str, count: int) -> str:
    shipment = register_shipment(client, tracking_number)
    # Delivered newest-first, so arrival order is the reverse of carrier time.
    for index in reversed(range(count)):
        post_event(
            client,
            carrier_event(
                "IN_TRANSIT" if index % 2 else "AT_DISTRIBUTION_CENTER",
                hours(index),
                tracking_number=tracking_number,
                event_id=f"{tracking_number}-{index}",
            ),
        )
    shipment_id: str = shipment["id"]
    return shipment_id


def test_timeline_is_ascending_by_carrier_time_by_default(client: TestClient) -> None:
    shipment_id = seed_timeline(client, "SCTIMELINE01", 5)

    timeline = get_timeline(client, shipment_id)

    assert [entry["provider_event_id"] for entry in timeline] == [
        f"SCTIMELINE01-{index}" for index in range(5)
    ]


def test_timeline_can_be_requested_newest_first(client: TestClient) -> None:
    shipment_id = seed_timeline(client, "SCTIMELINE01", 5)

    timeline = get_timeline(client, shipment_id, "?order=desc")

    assert [entry["provider_event_id"] for entry in timeline] == [
        f"SCTIMELINE01-{index}" for index in reversed(range(5))
    ]


def test_timeline_is_paginated(client: TestClient) -> None:
    shipment_id = seed_timeline(client, "SCTIMELINE01", 5)

    first = client.get(f"/shipments/{shipment_id}/events?limit=2").json()
    second = client.get(f"/shipments/{shipment_id}/events?limit=2&offset=2").json()
    third = client.get(f"/shipments/{shipment_id}/events?limit=2&offset=4").json()

    assert (first["total"], first["limit"], first["offset"]) == (5, 2, 0)
    pages = [first, second, third]
    assert [len(page["items"]) for page in pages] == [2, 2, 1]
    assert [item["provider_event_id"] for page in pages for item in page["items"]] == [
        f"SCTIMELINE01-{index}" for index in range(5)
    ]


def test_timeline_only_contains_the_requested_shipment(client: TestClient) -> None:
    first = seed_timeline(client, "SCTIMELINE01", 3)
    second = seed_timeline(client, "SCTIMELINE02", 2)

    assert {entry["shipment_id"] for entry in get_timeline(client, first)} == {first}
    assert len(get_timeline(client, second)) == 2


def test_events_with_the_same_carrier_time_are_ordered_by_receipt(client: TestClient) -> None:
    shipment = register_shipment(client)
    for event_id in ("first-received", "second-received", "third-received"):
        post_event(client, carrier_event("IN_TRANSIT", hours(4), event_id=event_id))

    timeline = get_timeline(client, shipment["id"])

    assert [entry["provider_event_id"] for entry in timeline] == [
        "first-received",
        "second-received",
        "third-received",
    ]


def test_timeline_of_shipment_without_events_is_empty(client: TestClient) -> None:
    shipment = register_shipment(client)

    page = client.get(f"/shipments/{shipment['id']}/events").json()

    assert page == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_timeline_of_unknown_shipment_returns_404(client: TestClient) -> None:
    response = client.get(f"/shipments/{uuid.uuid4()}/events")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "shipment_not_found"


def test_timeline_rejects_unknown_sort_order(client: TestClient) -> None:
    shipment = register_shipment(client)
    assert client.get(f"/shipments/{shipment['id']}/events?order=sideways").status_code == 422
