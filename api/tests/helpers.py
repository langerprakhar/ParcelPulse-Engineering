"""Builders shared by tests: carrier payloads and signed webhook requests."""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response

from parcelpulse_api.security import SIGNATURE_HEADER, build_signature_header

TEST_SIGNING_SECRET = "test-signing-secret-0123456789"
TRACKING_NUMBER = "SC4F7K2M9Q1X"

# A fixed point in the recent past; event times are expressed as hours after it.
JOURNEY_START = datetime.now(UTC).replace(microsecond=0) - timedelta(days=4)


def hours(count: float) -> datetime:
    return JOURNEY_START + timedelta(hours=count)


def carrier_event(
    event_type: str = "IN_TRANSIT",
    occurred_at: datetime | str | None = None,
    *,
    tracking_number: str = TRACKING_NUMBER,
    provider: str = "simcarrier",
    event_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if occurred_at is None:
        occurred_at = hours(4)
    payload: dict[str, Any] = {
        "provider": provider,
        "event_id": f"evt_{uuid.uuid4().hex}" if event_id is None else event_id,
        "tracking_number": tracking_number,
        "event_type": event_type,
        "occurred_at": occurred_at if isinstance(occurred_at, str) else occurred_at.isoformat(),
    }
    payload.update(extra)
    return payload


def signed_headers(
    body: bytes, *, secret: str = TEST_SIGNING_SECRET, timestamp: int | None = None
) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: build_signature_header(secret, body, timestamp or int(time.time())),
    }


def post_event(client: TestClient, payload: dict[str, Any], **signing: Any) -> Response:
    """Deliver a carrier event the way a carrier would: signed, as raw JSON."""
    body = json.dumps(payload).encode()
    return client.post("/webhooks/carrier", content=body, headers=signed_headers(body, **signing))


def register_shipment(
    client: TestClient, tracking_number: str = TRACKING_NUMBER, carrier: str = "simcarrier"
) -> dict[str, Any]:
    response = client.post(
        "/shipments", json={"tracking_number": tracking_number, "carrier": carrier}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def get_shipment(client: TestClient, shipment_id: str) -> dict[str, Any]:
    response = client.get(f"/shipments/{shipment_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def get_timeline(client: TestClient, shipment_id: str, query: str = "") -> list[dict[str, Any]]:
    response = client.get(f"/shipments/{shipment_id}/events{query}")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items
