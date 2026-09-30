"""Carrier webhook endpoint: authentication, validation and the effects of one delivery."""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from parcelpulse_api.correlation import CORRELATION_HEADER
from parcelpulse_api.main import create_app
from parcelpulse_api.models import ReceiptResult, TrackingEvent, WebhookReceipt
from tests.conftest import make_settings
from tests.helpers import (
    TRACKING_NUMBER,
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


def test_first_event_is_stored_and_updates_the_shipment(client: TestClient, db: Session) -> None:
    shipment = register_shipment(client)
    before = datetime.now(UTC)

    response = post_event(
        client,
        carrier_event(
            "IN_TRANSIT",
            hours(4),
            event_id="evt_transit_1",
            location={"facility": "Leeds Hub", "city": "Leeds", "region": "ENG", "country": "GB"},
            description="Departed origin facility",
            estimated_delivery_at=hours(52).isoformat(),
        ),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["result"] == "PROCESSED"
    assert result["duplicate"] is False
    assert result["shipment_id"] == shipment["id"]
    assert result["shipment_status"] == "IN_TRANSIT"

    updated = get_shipment(client, shipment["id"])
    assert updated["current_status"] == "IN_TRANSIT"
    assert datetime.fromisoformat(updated["last_event_at"]) == hours(4)
    assert datetime.fromisoformat(updated["estimated_delivery_at"]) == hours(52)

    event = db.get(TrackingEvent, uuid.UUID(result["tracking_event_id"]))
    assert event is not None
    assert event.provider == "simcarrier"
    assert event.provider_event_id == "evt_transit_1"
    # Carrier time and our receipt time are stored independently.
    assert event.event_at == hours(4)
    assert before <= event.received_at <= datetime.now(UTC)
    assert event.location == {
        "facility": "Leeds Hub",
        "city": "Leeds",
        "region": "ENG",
        "country": "GB",
    }
    assert event.description == "Departed origin facility"
    assert event.changed_status is True
    assert event.arrived_out_of_order is False
    assert event.status_after == "IN_TRANSIT"

    receipt = db.get(WebhookReceipt, uuid.UUID(result["receipt_id"]))
    assert receipt is not None
    assert receipt.result is ReceiptResult.PROCESSED
    assert receipt.is_duplicate is False
    assert receipt.tracking_event_id == event.id
    assert receipt.payload_hash == event.payload_hash


def test_event_appears_in_the_timeline_with_both_timestamps(client: TestClient) -> None:
    shipment = register_shipment(client)
    post_event(client, carrier_event("LABEL_CREATED", hours(0), location={"city": "Leeds"}))

    (entry,) = get_timeline(client, shipment["id"])

    assert entry["event_type"] == "LABEL_CREATED"
    assert datetime.fromisoformat(entry["event_at"]) == hours(0)
    assert datetime.fromisoformat(entry["received_at"]) > hours(0)
    assert entry["location"] == {"city": "Leeds"}
    assert "payload" not in entry


def test_unknown_carrier_fields_are_kept_in_the_stored_payload(
    client: TestClient, db: Session
) -> None:
    register_shipment(client)
    payload = carrier_event(service_level="express", pieces=[{"weight_kg": 1.2}])

    result = post_event(client, payload).json()

    event = db.get(TrackingEvent, uuid.UUID(result["tracking_event_id"]))
    assert event is not None
    assert event.payload == payload


def test_event_for_untracked_shipment_is_acknowledged_but_not_stored(
    client: TestClient, db: Session
) -> None:
    response = post_event(client, carrier_event(tracking_number="SCNOBODY0001"))

    assert response.status_code == 200
    result = response.json()
    assert result["result"] == "UNKNOWN_SHIPMENT"
    assert result["shipment_id"] is None
    assert result["tracking_event_id"] is None
    assert count(db, TrackingEvent) == 0

    receipt = db.get(WebhookReceipt, uuid.UUID(result["receipt_id"]))
    assert receipt is not None
    assert receipt.result is ReceiptResult.UNKNOWN_SHIPMENT
    assert receipt.tracking_number == "SCNOBODY0001"


def test_event_from_a_different_carrier_does_not_touch_the_shipment(client: TestClient) -> None:
    shipment = register_shipment(client)

    result = post_event(client, carrier_event("DELIVERED", provider="othercarrier")).json()

    assert result["result"] == "UNKNOWN_SHIPMENT"
    assert get_shipment(client, shipment["id"])["current_status"] == "CREATED"


def test_correlation_id_is_recorded_on_event_and_receipt(client: TestClient, db: Session) -> None:
    register_shipment(client)
    body = json.dumps(carrier_event()).encode()

    response = client.post(
        "/webhooks/carrier",
        content=body,
        headers={**signed_headers(body), CORRELATION_HEADER: "carrier-delivery-7781"},
    )

    result = response.json()
    assert response.headers[CORRELATION_HEADER] == "carrier-delivery-7781"
    event = db.get(TrackingEvent, uuid.UUID(result["tracking_event_id"]))
    receipt = db.get(WebhookReceipt, uuid.UUID(result["receipt_id"]))
    assert event is not None and event.correlation_id == "carrier-delivery-7781"
    assert receipt is not None and receipt.correlation_id == "carrier-delivery-7781"


# --- Authentication ---------------------------------------------------------


def assert_rejected_without_side_effects(response: Response, db: Session) -> None:
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_webhook_signature"
    assert count(db, TrackingEvent) == 0
    assert count(db, WebhookReceipt) == 0


def test_unsigned_webhook_is_rejected(client: TestClient, db: Session) -> None:
    register_shipment(client)
    response = client.post("/webhooks/carrier", json=carrier_event())
    assert_rejected_without_side_effects(response, db)


def test_webhook_signed_with_wrong_secret_is_rejected(client: TestClient, db: Session) -> None:
    register_shipment(client)
    response = post_event(client, carrier_event(), secret="not-the-shared-secret-000000")
    assert_rejected_without_side_effects(response, db)


def test_webhook_with_stale_signature_is_rejected(client: TestClient, db: Session) -> None:
    register_shipment(client)
    response = post_event(client, carrier_event(), timestamp=int(time.time()) - 3600)
    assert_rejected_without_side_effects(response, db)


def test_webhook_with_tampered_body_is_rejected(client: TestClient, db: Session) -> None:
    register_shipment(client)
    signed_body = json.dumps(carrier_event("IN_TRANSIT", event_id="evt_1")).encode()
    tampered_body = signed_body.replace(b"IN_TRANSIT", b"DELIVERED")

    response = client.post(
        "/webhooks/carrier", content=tampered_body, headers=signed_headers(signed_body)
    )

    assert_rejected_without_side_effects(response, db)


def test_signature_failure_does_not_reveal_the_reason(client: TestClient) -> None:
    response = post_event(client, carrier_event(), timestamp=int(time.time()) - 3600)
    assert response.json()["error"]["message"] == "Webhook signature verification failed"
    assert "tolerance" not in response.text


def test_signature_can_be_disabled_outside_production(database_url: str, db: Session) -> None:
    settings = make_settings(database_url=database_url, webhook_signature_required=False)
    with TestClient(create_app(settings)) as client:
        register_shipment(client)
        response = client.post("/webhooks/carrier", json=carrier_event())

    assert response.status_code == 200
    assert response.json()["result"] == "PROCESSED"


# --- Validation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("occurred_at", "2026-09-01T08:00:00"),
        ("event_type", "TELEPORTED"),
        ("event_id", "has spaces"),
        ("tracking_number", "bad!"),
    ],
)
def test_invalid_payload_is_rejected_without_side_effects(
    client: TestClient, db: Session, field: str, value: str
) -> None:
    register_shipment(client)

    response = post_event(client, carrier_event(**{field: value}))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", field]
    assert count(db, TrackingEvent) == 0
    assert count(db, WebhookReceipt) == 0


def test_event_dated_far_in_the_future_is_rejected(client: TestClient, db: Session) -> None:
    shipment = register_shipment(client)
    tomorrow = datetime.now(UTC) + timedelta(days=1)

    response = post_event(client, carrier_event("DELIVERED", tomorrow))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "event_time_in_future"
    assert count(db, TrackingEvent) == 0
    assert get_shipment(client, shipment["id"])["current_status"] == "CREATED"


def test_event_within_clock_skew_allowance_is_accepted(client: TestClient) -> None:
    register_shipment(client)
    slightly_ahead = datetime.now(UTC) + timedelta(minutes=5)

    response = post_event(client, carrier_event("IN_TRANSIT", slightly_ahead))

    assert response.status_code == 200
    assert response.json()["result"] == "PROCESSED"


def test_oversized_body_is_rejected(client: TestClient, db: Session) -> None:
    register_shipment(client)

    response = post_event(client, carrier_event(description_blob="x" * 70_000))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert count(db, WebhookReceipt) == 0


def test_tracking_number_in_payload_is_normalized(client: TestClient) -> None:
    shipment = register_shipment(client)

    result = post_event(client, carrier_event(tracking_number=TRACKING_NUMBER.lower())).json()

    assert result["result"] == "PROCESSED"
    assert result["shipment_id"] == shipment["id"]
