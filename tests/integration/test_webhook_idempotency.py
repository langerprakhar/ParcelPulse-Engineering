"""Carrier retries: redelivering an event must not duplicate or corrupt anything."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from parcelpulse_api.main import create_app
from parcelpulse_api.models import ReceiptResult, Shipment, TrackingEvent, WebhookReceipt, utcnow
from parcelpulse_api.routers import webhooks as webhooks_router
from parcelpulse_api.schemas import CarrierEventPayload
from parcelpulse_api.services.webhooks import ingest_carrier_event
from tests.conftest import make_settings
from tests.helpers import (
    carrier_event,
    get_shipment,
    get_timeline,
    hours,
    post_event,
    register_shipment,
    signed_headers,
)


def count(db: Session, model: type) -> int:
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def receipts(db: Session) -> list[WebhookReceipt]:
    return list(
        db.execute(select(WebhookReceipt).order_by(WebhookReceipt.received_at)).scalars().all()
    )


def test_redelivered_event_is_acknowledged_as_duplicate(client: TestClient, db: Session) -> None:
    shipment = register_shipment(client)
    payload = carrier_event("IN_TRANSIT", hours(4), estimated_delivery_at=hours(52).isoformat())

    first = post_event(client, payload)
    after_first = get_shipment(client, shipment["id"])
    second = post_event(client, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["result"] == "PROCESSED"
    duplicate = second.json()
    assert duplicate["result"] == "DUPLICATE"
    assert duplicate["duplicate"] is True
    # The duplicate points at the event stored by the first delivery.
    assert duplicate["tracking_event_id"] == first.json()["tracking_event_id"]
    assert duplicate["shipment_status"] == "IN_TRANSIT"

    assert count(db, TrackingEvent) == 1
    assert len(get_timeline(client, shipment["id"])) == 1
    # Nothing about the shipment changed, not even its modification time.
    assert get_shipment(client, shipment["id"]) == after_first


def test_every_delivery_attempt_leaves_a_receipt(client: TestClient, db: Session) -> None:
    register_shipment(client)
    payload = carrier_event()

    for _ in range(4):
        assert post_event(client, payload).status_code == 200

    recorded = receipts(db)
    assert [receipt.result for receipt in recorded] == [
        ReceiptResult.PROCESSED,
        ReceiptResult.DUPLICATE,
        ReceiptResult.DUPLICATE,
        ReceiptResult.DUPLICATE,
    ]
    assert [receipt.is_duplicate for receipt in recorded] == [False, True, True, True]
    assert len({receipt.tracking_event_id for receipt in recorded}) == 1
    assert len({receipt.payload_hash for receipt in recorded}) == 1
    assert count(db, TrackingEvent) == 1


def test_duplicate_is_recognized_when_the_body_is_reserialized(
    client: TestClient, db: Session
) -> None:
    register_shipment(client)
    payload = carrier_event(location={"city": "Leeds", "country": "GB"})
    post_event(client, payload)

    # Same event, different key order and whitespace, freshly signed.
    reordered = json.dumps(dict(reversed(payload.items())), indent=2).encode()
    response = client.post(
        "/webhooks/carrier", content=reordered, headers=signed_headers(reordered)
    )

    assert response.json()["result"] == "DUPLICATE"
    assert count(db, TrackingEvent) == 1


def test_late_retry_of_an_old_event_does_not_rewind_the_shipment(
    client: TestClient, db: Session
) -> None:
    shipment = register_shipment(client)
    in_transit = carrier_event("IN_TRANSIT", hours(4))
    post_event(client, in_transit)
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))
    post_event(client, carrier_event("DELIVERED", hours(50)))

    # The carrier retries the very first event long after the parcel arrived.
    retry = post_event(client, in_transit).json()

    assert retry["result"] == "DUPLICATE"
    assert retry["shipment_status"] == "DELIVERED"
    assert get_shipment(client, shipment["id"])["current_status"] == "DELIVERED"
    assert count(db, TrackingEvent) == 3


def test_same_event_id_with_different_content_keeps_the_original(
    client: TestClient, db: Session
) -> None:
    shipment = register_shipment(client)
    original = carrier_event("IN_TRANSIT", hours(4), event_id="evt_reused")
    conflicting = carrier_event("DELIVERED", hours(50), event_id="evt_reused")
    post_event(client, original)

    response = post_event(client, conflicting)

    assert response.status_code == 200
    result = response.json()
    assert result["result"] == "DUPLICATE_PAYLOAD_MISMATCH"
    assert result["duplicate"] is True
    assert get_shipment(client, shipment["id"])["current_status"] == "IN_TRANSIT"

    (stored,) = db.execute(select(TrackingEvent)).scalars().all()
    assert stored.event_type == "IN_TRANSIT"
    assert stored.payload == original
    assert receipts(db)[-1].result is ReceiptResult.DUPLICATE_PAYLOAD_MISMATCH


def test_event_ids_are_scoped_to_the_provider(database_url: str, db: Session) -> None:
    settings = make_settings(
        database_url=database_url, supported_carriers=["simcarrier", "othercarrier"]
    )
    with TestClient(create_app(settings)) as client:
        first = register_shipment(client, "SCAAAA000001", "simcarrier")
        second = register_shipment(client, "OCBBBB000002", "othercarrier")

        one = post_event(
            client, carrier_event("IN_TRANSIT", tracking_number="SCAAAA000001", event_id="1001")
        ).json()
        two = post_event(
            client,
            carrier_event(
                "DELIVERED",
                tracking_number="OCBBBB000002",
                provider="othercarrier",
                event_id="1001",
            ),
        ).json()

        assert one["result"] == "PROCESSED"
        assert two["result"] == "PROCESSED"
        assert get_shipment(client, first["id"])["current_status"] == "IN_TRANSIT"
        assert get_shipment(client, second["id"])["current_status"] == "DELIVERED"
    assert count(db, TrackingEvent) == 2


def test_failed_delivery_leaves_nothing_behind_and_its_retry_is_processed(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after the event was written but before commit must roll everything back."""
    shipment = register_shipment(client)
    payload = carrier_event("OUT_FOR_DELIVERY", hours(44))

    def ingest_then_crash(*args: Any, **kwargs: Any) -> None:
        ingest_carrier_event(*args, **kwargs)
        raise RuntimeError("process died before commit")

    monkeypatch.setattr(webhooks_router, "ingest_carrier_event", ingest_then_crash)
    failed = post_event(client, payload)

    assert failed.status_code == 500
    assert count(db, TrackingEvent) == 0
    assert count(db, WebhookReceipt) == 0
    assert get_shipment(client, shipment["id"])["current_status"] == "CREATED"

    monkeypatch.undo()
    retried = post_event(client, payload)

    # The retry is not mistaken for a duplicate: nothing was committed the first time.
    assert retried.status_code == 200
    assert retried.json()["result"] == "PROCESSED"
    assert get_shipment(client, shipment["id"])["current_status"] == "OUT_FOR_DELIVERY"
    assert count(db, TrackingEvent) == 1


def ingest_in_own_transaction(
    session_factory: sessionmaker[Session], payload: dict[str, Any]
) -> ReceiptResult:
    with session_factory() as session, session.begin():
        outcome = ingest_carrier_event(
            session,
            CarrierEventPayload.model_validate(payload),
            raw_payload=payload,
            received_at=utcnow(),
        )
        return outcome.result


def test_concurrent_deliveries_of_one_event_store_it_exactly_once(
    client: TestClient, session_factory: sessionmaker[Session], db: Session
) -> None:
    shipment = register_shipment(client)
    payload = carrier_event("OUT_FOR_DELIVERY", hours(44))
    attempts = 12

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        results = list(
            pool.map(lambda _: ingest_in_own_transaction(session_factory, payload), range(attempts))
        )

    assert results.count(ReceiptResult.PROCESSED) == 1
    assert results.count(ReceiptResult.DUPLICATE) == attempts - 1
    assert count(db, TrackingEvent) == 1
    assert count(db, WebhookReceipt) == attempts
    assert get_shipment(client, shipment["id"])["current_status"] == "OUT_FOR_DELIVERY"


def test_concurrent_distinct_events_for_one_shipment_converge_on_the_right_state(
    client: TestClient, session_factory: sessionmaker[Session], db: Session
) -> None:
    shipment = register_shipment(client)
    payloads = [
        carrier_event("LABEL_CREATED", hours(0)),
        carrier_event("IN_TRANSIT", hours(4)),
        carrier_event("AT_DISTRIBUTION_CENTER", hours(20)),
        carrier_event("OUT_FOR_DELIVERY", hours(44)),
        carrier_event("DELIVERED", hours(50)),
    ]
    # Each event is delivered three times, all at once.
    deliveries = payloads * 3

    with ThreadPoolExecutor(max_workers=len(deliveries)) as pool:
        results = list(
            pool.map(lambda item: ingest_in_own_transaction(session_factory, item), deliveries)
        )

    assert results.count(ReceiptResult.PROCESSED) == len(payloads)
    assert results.count(ReceiptResult.DUPLICATE) == len(deliveries) - len(payloads)
    assert count(db, TrackingEvent) == len(payloads)

    stored = db.get(Shipment, uuid.UUID(shipment["id"]))
    assert stored is not None
    assert stored.current_status == "DELIVERED"
    assert stored.last_event_at == hours(50)
    # Arrival order was arbitrary, but the DELIVERED event always causes a transition.
    transitions = db.execute(
        select(TrackingEvent.status_after).where(TrackingEvent.changed_status.is_(True))
    ).scalars()
    assert "DELIVERED" in set(transitions)
