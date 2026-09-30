"""The notification outbox: which events owe a notification, and exactly how many."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from parcelpulse_api.correlation import CORRELATION_HEADER
from parcelpulse_api.models import Notification, NotificationStatus, utcnow
from parcelpulse_api.queue import InMemoryNotificationPublisher
from parcelpulse_api.routers import webhooks as webhooks_router
from parcelpulse_api.schemas import CarrierEventPayload
from parcelpulse_api.services.webhooks import ingest_carrier_event
from tests.helpers import (
    TRACKING_NUMBER,
    carrier_event,
    hours,
    post_event,
    register_shipment,
    signed_headers,
)

EMAIL = "recipient@example.com"


def register_with_email(client: TestClient, tracking_number: str = TRACKING_NUMBER) -> dict:
    response = client.post(
        "/shipments",
        json={
            "tracking_number": tracking_number,
            "carrier": "simcarrier",
            "notification_email": EMAIL,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def notifications(db: Session) -> list[Notification]:
    db.expire_all()
    return list(db.execute(select(Notification).order_by(Notification.created_at)).scalars().all())


@pytest.mark.parametrize("event_type", ["OUT_FOR_DELIVERY", "DELIVERED", "DELIVERY_EXCEPTION"])
def test_notifiable_event_creates_one_pending_notification_and_publishes_it(
    client: TestClient, db: Session, publisher: InMemoryNotificationPublisher, event_type: str
) -> None:
    shipment = register_with_email(client)

    result = post_event(client, carrier_event(event_type, hours(44))).json()

    (notification,) = notifications(db)
    assert notification.type == event_type
    assert notification.channel == "EMAIL"
    assert notification.destination == EMAIL
    assert notification.status is NotificationStatus.PENDING
    assert notification.attempts == 0
    assert notification.sent_at is None
    assert str(notification.shipment_id) == shipment["id"]
    assert str(notification.tracking_event_id) == result["tracking_event_id"]
    assert [published_id for published_id, _ in publisher.published] == [notification.id]


@pytest.mark.parametrize(
    "event_type", ["LABEL_CREATED", "IN_TRANSIT", "AT_DISTRIBUTION_CENTER", "RETURNED"]
)
def test_other_events_do_not_notify(
    client: TestClient, db: Session, publisher: InMemoryNotificationPublisher, event_type: str
) -> None:
    register_with_email(client)

    post_event(client, carrier_event(event_type, hours(4)))

    assert notifications(db) == []
    assert publisher.published == []


def test_redelivered_webhook_does_not_create_or_publish_a_second_notification(
    client: TestClient, db: Session, publisher: InMemoryNotificationPublisher
) -> None:
    register_with_email(client)
    payload = carrier_event("OUT_FOR_DELIVERY", hours(44))

    results = [post_event(client, payload).json()["result"] for _ in range(5)]

    assert results == ["PROCESSED", "DUPLICATE", "DUPLICATE", "DUPLICATE", "DUPLICATE"]
    assert len(notifications(db)) == 1
    assert len(publisher.published) == 1


def test_concurrent_redeliveries_create_exactly_one_notification(
    client: TestClient, session_factory: sessionmaker[Session], db: Session
) -> None:
    register_with_email(client)
    payload = carrier_event("DELIVERED", hours(50))

    def deliver(_: int) -> int:
        with session_factory() as session, session.begin():
            outcome = ingest_carrier_event(
                session,
                CarrierEventPayload.model_validate(payload),
                raw_payload=payload,
                received_at=utcnow(),
            )
            return len(outcome.notification_ids)

    with ThreadPoolExecutor(max_workers=12) as pool:
        planned = list(pool.map(deliver, range(12)))

    assert sum(planned) == 1
    assert len(notifications(db)) == 1


def test_no_notification_without_an_email_address(
    client: TestClient, db: Session, publisher: InMemoryNotificationPublisher
) -> None:
    register_shipment(client)

    post_event(client, carrier_event("DELIVERED", hours(50)))

    assert notifications(db) == []
    assert publisher.published == []


def test_disabled_notification_type_is_skipped_while_others_still_send(
    client: TestClient, db: Session
) -> None:
    shipment = register_with_email(client)
    client.put(
        f"/shipments/{shipment['id']}/notification-preferences",
        json={"email": EMAIL, "notify_out_for_delivery": False},
    )

    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))
    post_event(client, carrier_event("DELIVERED", hours(50)))

    assert [notification.type for notification in notifications(db)] == ["DELIVERED"]


def test_late_historical_event_does_not_notify(
    client: TestClient, db: Session, publisher: InMemoryNotificationPublisher
) -> None:
    """Out for delivery, reported after the parcel was already delivered, is old news."""
    register_with_email(client)
    post_event(client, carrier_event("DELIVERED", hours(50)))

    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))
    post_event(client, carrier_event("DELIVERY_EXCEPTION", hours(47)))

    assert [notification.type for notification in notifications(db)] == ["DELIVERED"]
    assert len(publisher.published) == 1


def test_second_delivered_event_with_a_new_id_does_not_notify_again(
    client: TestClient, db: Session
) -> None:
    register_with_email(client)
    post_event(client, carrier_event("DELIVERED", hours(50), event_id="evt_delivered"))

    # A carrier "proof of delivery" follow-up: a distinct event, same status.
    result = post_event(
        client, carrier_event("DELIVERED", hours(50.5), event_id="evt_delivered_pod")
    ).json()

    assert result["result"] == "PROCESSED"
    assert len(notifications(db)) == 1


def test_each_real_status_change_notifies_once(client: TestClient, db: Session) -> None:
    register_with_email(client)
    for event_type, offset in [
        ("OUT_FOR_DELIVERY", 44),
        ("DELIVERY_EXCEPTION", 47),
        ("OUT_FOR_DELIVERY", 68),
        ("DELIVERED", 72),
    ]:
        payload = carrier_event(event_type, hours(offset))
        post_event(client, payload)
        post_event(client, payload)  # every event is also retried by the carrier

    assert [notification.type for notification in notifications(db)] == [
        "OUT_FOR_DELIVERY",
        "DELIVERY_EXCEPTION",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
    ]


def test_notification_is_committed_before_it_is_published(
    client: TestClient,
    session_factory: sessionmaker[Session],
    publisher: InMemoryNotificationPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker must be able to read the row as soon as it receives the message."""
    register_with_email(client)
    visible_at_publish: list[bool] = []
    original_publish = publisher.publish

    def publish_and_check(notification_id: uuid.UUID, **kwargs: Any) -> None:
        with session_factory() as other_connection:
            visible_at_publish.append(
                other_connection.get(Notification, notification_id) is not None
            )
        original_publish(notification_id, **kwargs)

    monkeypatch.setattr(publisher, "publish", publish_and_check)
    post_event(client, carrier_event("DELIVERED", hours(50)))

    assert visible_at_publish == [True]


def test_broker_outage_does_not_fail_the_webhook_or_lose_the_notification(
    client: TestClient, db: Session, publisher: InMemoryNotificationPublisher
) -> None:
    register_with_email(client)
    publisher.fail_with = ConnectionError("redis is down")

    response = post_event(client, carrier_event("DELIVERED", hours(50)))

    assert response.status_code == 200
    assert response.json()["result"] == "PROCESSED"
    (notification,) = notifications(db)
    assert notification.status is NotificationStatus.PENDING


def test_failed_delivery_rolls_back_the_notification_with_the_event(
    client: TestClient,
    db: Session,
    publisher: InMemoryNotificationPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_with_email(client)
    payload = carrier_event("DELIVERED", hours(50))

    def ingest_then_crash(*args: Any, **kwargs: Any) -> None:
        ingest_carrier_event(*args, **kwargs)
        raise RuntimeError("process died before commit")

    monkeypatch.setattr(webhooks_router, "ingest_carrier_event", ingest_then_crash)
    assert post_event(client, payload).status_code == 500
    assert notifications(db) == []
    assert publisher.published == []

    monkeypatch.undo()
    assert post_event(client, payload).json()["result"] == "PROCESSED"
    assert len(notifications(db)) == 1
    assert len(publisher.published) == 1


def test_correlation_id_travels_with_the_notification(
    client: TestClient, db: Session, publisher: InMemoryNotificationPublisher
) -> None:
    register_with_email(client)
    body = json.dumps(carrier_event("DELIVERED", hours(50))).encode()

    client.post(
        "/webhooks/carrier",
        content=body,
        headers={**signed_headers(body), CORRELATION_HEADER: "carrier-delivery-9001"},
    )

    (notification,) = notifications(db)
    assert notification.correlation_id == "carrier-delivery-9001"
    assert publisher.published == [(notification.id, "carrier-delivery-9001")]


# --- Preferences and history endpoints --------------------------------------


def test_preferences_default_to_no_address_and_everything_enabled(client: TestClient) -> None:
    shipment = register_shipment(client)

    response = client.get(f"/shipments/{shipment['id']}/notification-preferences")

    assert response.status_code == 200
    assert response.json() == {
        "shipment_id": shipment["id"],
        "email": None,
        "notify_out_for_delivery": True,
        "notify_delivered": True,
        "notify_delivery_exception": True,
        "updated_at": None,
    }


def test_registration_email_becomes_the_preference(client: TestClient) -> None:
    shipment = register_with_email(client)

    preference = client.get(f"/shipments/{shipment['id']}/notification-preferences").json()

    assert preference["email"] == EMAIL
    assert preference["updated_at"] is not None


def test_preferences_can_be_saved_and_replaced(client: TestClient, db: Session) -> None:
    shipment = register_shipment(client)
    url = f"/shipments/{shipment['id']}/notification-preferences"

    first = client.put(url, json={"email": EMAIL, "notify_delivered": False})
    second = client.put(url, json={"email": "other@example.com"})

    assert first.status_code == 200
    assert first.json()["notify_delivered"] is False
    assert second.json()["email"] == "other@example.com"
    # PUT replaces: flags omitted from the second request are back to their defaults.
    assert second.json()["notify_delivered"] is True
    assert client.get(url).json() == second.json()


def test_clearing_the_email_stops_notifications(client: TestClient, db: Session) -> None:
    shipment = register_with_email(client)
    client.put(f"/shipments/{shipment['id']}/notification-preferences", json={"email": None})

    post_event(client, carrier_event("DELIVERED", hours(50)))

    assert notifications(db) == []


def test_preference_change_only_affects_later_events(client: TestClient, db: Session) -> None:
    shipment = register_with_email(client)
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))

    client.put(
        f"/shipments/{shipment['id']}/notification-preferences",
        json={"email": "new-address@example.com"},
    )
    post_event(client, carrier_event("DELIVERED", hours(50)))

    assert [(n.type, n.destination) for n in notifications(db)] == [
        ("OUT_FOR_DELIVERY", EMAIL),
        ("DELIVERED", "new-address@example.com"),
    ]


def test_invalid_email_is_rejected(client: TestClient) -> None:
    shipment = register_shipment(client)

    response = client.put(
        f"/shipments/{shipment['id']}/notification-preferences", json={"email": "not-an-email"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["body", "email"]


def test_registration_with_invalid_email_creates_nothing(client: TestClient, db: Session) -> None:
    response = client.post(
        "/shipments",
        json={
            "tracking_number": TRACKING_NUMBER,
            "carrier": "simcarrier",
            "notification_email": "x",
        },
    )

    assert response.status_code == 422
    assert client.get(f"/shipments/by-tracking/{TRACKING_NUMBER}").status_code == 404


def test_preferences_of_unknown_shipment_return_404(client: TestClient) -> None:
    url = f"/shipments/{uuid.uuid4()}/notification-preferences"
    assert client.get(url).status_code == 404
    assert client.put(url, json={"email": EMAIL}).status_code == 404


def test_notification_history_lists_newest_first(client: TestClient) -> None:
    shipment = register_with_email(client)
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))
    post_event(client, carrier_event("DELIVERED", hours(50)))

    page = client.get(f"/shipments/{shipment['id']}/notifications").json()

    assert page["total"] == 2
    assert [item["type"] for item in page["items"]] == ["DELIVERED", "OUT_FOR_DELIVERY"]
    assert page["items"][0] == {
        "id": page["items"][0]["id"],
        "shipment_id": shipment["id"],
        "tracking_event_id": page["items"][0]["tracking_event_id"],
        "type": "DELIVERED",
        "channel": "EMAIL",
        "destination": EMAIL,
        "status": "PENDING",
        "attempts": 0,
        "created_at": page["items"][0]["created_at"],
        "sent_at": None,
        "last_error": None,
    }


def test_notification_history_is_paginated_and_scoped(client: TestClient) -> None:
    shipment = register_with_email(client)
    other = register_with_email(client, "SCOTHER00001")
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))
    post_event(client, carrier_event("DELIVERED", hours(50)))
    post_event(client, carrier_event("DELIVERED", hours(50), tracking_number="SCOTHER00001"))

    page = client.get(f"/shipments/{shipment['id']}/notifications?limit=1&offset=1").json()

    assert (page["total"], len(page["items"])) == (2, 1)
    assert page["items"][0]["type"] == "OUT_FOR_DELIVERY"
    assert client.get(f"/shipments/{other['id']}/notifications").json()["total"] == 1


def test_notification_history_of_unknown_shipment_returns_404(client: TestClient) -> None:
    assert client.get(f"/shipments/{uuid.uuid4()}/notifications").status_code == 404
