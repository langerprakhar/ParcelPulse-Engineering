"""A fake ParcelPulse that the simulator talks to over a mock HTTP transport."""

import hashlib
import hmac
import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest

from carrier_simulator.config import Settings
from carrier_simulator.sender import WebhookSender
from carrier_simulator.simulator import Simulator

SECRET = "simulator-test-secret-0123456789"
WEBHOOK_URL = "http://parcelpulse.test/webhooks/carrier"
API_URL = "http://parcelpulse.test"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@dataclass
class ReceivedWebhook:
    body: bytes
    signature: str
    payload: dict[str, Any]


@dataclass
class FakeParcelPulse:
    """Verifies signatures and deduplicates by event id, like the real receiver."""

    webhooks: list[ReceivedWebhook] = field(default_factory=list)
    registrations: list[dict[str, Any]] = field(default_factory=list)
    # Scripted responses for the next webhook requests: a status code, or an
    # exception to raise instead of responding.
    scripted: list[int | Exception] = field(default_factory=list)
    registration_status: int = 201
    seen_event_ids: set[str] = field(default_factory=set)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/shipments":
            self.registrations.append(json.loads(request.content))
            return httpx2.Response(self.registration_status, json={"id": "fake"})

        assert request.url.path == "/webhooks/carrier"
        signature = request.headers["X-Carrier-Signature"]
        self.webhooks.append(
            ReceivedWebhook(
                body=request.content, signature=signature, payload=json.loads(request.content)
            )
        )
        if self.scripted:
            scripted = self.scripted.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            if scripted != 200:
                return httpx2.Response(scripted, json={"error": {"code": f"http_{scripted}"}})

        if not signature_is_valid(signature, request.content):
            return httpx2.Response(401, json={"error": {"code": "invalid_webhook_signature"}})

        event_id = json.loads(request.content)["event_id"]
        result = "DUPLICATE" if event_id in self.seen_event_ids else "PROCESSED"
        self.seen_event_ids.add(event_id)
        return httpx2.Response(200, json={"result": result})

    @property
    def event_types(self) -> list[str]:
        return [webhook.payload["event_type"] for webhook in self.webhooks]


def signature_is_valid(header: str, body: bytes) -> bool:
    parts = dict(part.split("=", 1) for part in header.split(","))
    expected = hmac.new(
        SECRET.encode(), f"{parts['t']}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])


@pytest.fixture
def receiver() -> FakeParcelPulse:
    return FakeParcelPulse()


@pytest.fixture
def http_client(receiver: FakeParcelPulse) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(receiver.handle))


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def sender(http_client: httpx2.Client, sleeps: list[float]) -> WebhookSender:
    return WebhookSender(
        http_client,
        url=WEBHOOK_URL,
        secret=SECRET,
        max_attempts=4,
        backoff_seconds=0.5,
        sleep=sleeps.append,
    )


@pytest.fixture
def simulator(sender: WebhookSender, http_client: httpx2.Client) -> Simulator:
    def register(tracking_number: str, notification_email: str | None) -> None:
        body: dict[str, Any] = {"tracking_number": tracking_number, "carrier": "simcarrier"}
        if notification_email:
            body["notification_email"] = notification_email
        http_client.post(f"{API_URL}/shipments", json=body)

    return Simulator(
        sender,
        carrier_code="simcarrier",
        register=register,
        clock=lambda: NOW,
        rng=random.Random(7),
    )


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "webhook_url": WEBHOOK_URL,
        "webhook_signing_secret": SECRET,
        "parcelpulse_api_url": API_URL,
        "webhook_retry_backoff_seconds": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]
