"""Readiness, metrics and the development namespace."""

from fastapi.testclient import TestClient

from parcelpulse_api.main import create_app
from parcelpulse_api.queue import InMemoryNotificationPublisher
from tests.conftest import make_settings
from tests.helpers import carrier_event, get_shipment, hours, post_event, register_shipment


def metric_lines(client: TestClient) -> list[str]:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    return response.text.splitlines()


def test_ready_when_database_and_broker_respond(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}


def test_not_ready_when_the_broker_is_down(
    client: TestClient, publisher: InMemoryNotificationPublisher
) -> None:
    publisher.fail_with = ConnectionError("redis://:s3cret@redis:6379 refused")

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "redis": "error"},
    }
    assert "s3cret" not in response.text


def test_liveness_does_not_depend_on_the_broker(
    client: TestClient, publisher: InMemoryNotificationPublisher
) -> None:
    publisher.fail_with = ConnectionError("down")
    assert client.get("/health").status_code == 200


def test_metrics_count_webhook_results(client: TestClient) -> None:
    register_shipment(client)
    payload = carrier_event("OUT_FOR_DELIVERY", hours(44))
    post_event(client, payload)
    post_event(client, payload)
    post_event(client, carrier_event("IN_TRANSIT", hours(4)))
    post_event(client, carrier_event(tracking_number="SCNOBODY0001"))
    post_event(client, carrier_event(), secret="not-the-shared-secret-000000")

    lines = metric_lines(client)

    assert 'parcelpulse_webhook_deliveries_total{result="PROCESSED"} 2.0' in lines
    assert 'parcelpulse_webhook_deliveries_total{result="DUPLICATE"} 1.0' in lines
    assert 'parcelpulse_webhook_deliveries_total{result="UNKNOWN_SHIPMENT"} 1.0' in lines
    assert 'parcelpulse_webhook_rejections_total{reason="invalid_signature"} 1.0' in lines
    assert "parcelpulse_tracking_events_out_of_order_total 1.0" in lines


def test_metrics_count_planned_notifications_and_publish_failures(
    client: TestClient, publisher: InMemoryNotificationPublisher
) -> None:
    client.post(
        "/shipments",
        json={
            "tracking_number": "SC4F7K2M9Q1X",
            "carrier": "simcarrier",
            "notification_email": "recipient@example.com",
        },
    )
    post_event(client, carrier_event("OUT_FOR_DELIVERY", hours(44)))
    publisher.fail_with = ConnectionError("redis is down")
    post_event(client, carrier_event("DELIVERED", hours(50)))
    publisher.fail_with = None

    lines = metric_lines(client)

    assert "parcelpulse_notifications_planned_total 2.0" in lines
    assert "parcelpulse_notification_publish_failures_total 1.0" in lines


def test_http_metrics_are_labelled_by_route_template(client: TestClient) -> None:
    shipment = register_shipment(client)
    get_shipment(client, shipment["id"])
    client.get("/shipments/00000000-0000-0000-0000-000000000000")

    text = "\n".join(metric_lines(client))

    series = 'parcelpulse_http_requests_total{method="GET",route="/shipments/{shipment_id}"'
    assert series + ',status="200"} 1.0' in text
    assert series + ',status="404"} 1.0' in text
    assert shipment["id"] not in text


def test_dev_endpoints_are_absent_by_default(client: TestClient) -> None:
    assert client.get("/dev/webhook-receipts").status_code == 404
    assert not any(path.startswith("/dev") for path in client.get("/openapi.json").json()["paths"])


def test_dev_receipts_show_every_delivery_attempt(database_url: str) -> None:
    settings = make_settings(database_url=database_url, enable_dev_endpoints=True)
    app = create_app(settings, notification_publisher=InMemoryNotificationPublisher())
    with TestClient(app) as client:
        register_shipment(client)
        payload = carrier_event("IN_TRANSIT", hours(4), event_id="evt_retry_me")
        post_event(client, payload)
        post_event(client, payload)
        post_event(client, carrier_event("DELIVERED", hours(50), event_id="evt_other"))

        everything = client.get("/dev/webhook-receipts").json()
        for_event = client.get("/dev/webhook-receipts?provider_event_id=evt_retry_me").json()
        for_tracking = client.get("/dev/webhook-receipts?tracking_number=sc4f7k2m9q1x").json()

    assert everything["total"] == 3
    assert for_tracking["total"] == 3
    assert [(item["result"], item["is_duplicate"]) for item in for_event["items"]] == [
        ("PROCESSED", False),
        ("DUPLICATE", True),
    ]
    assert len({item["tracking_event_id"] for item in for_event["items"]}) == 1


def test_openapi_document_describes_the_public_api(client: TestClient) -> None:
    document = client.get("/openapi.json").json()

    assert document["info"]["title"] == "ParcelPulse API"
    assert {
        "/shipments",
        "/shipments/{shipment_id}",
        "/shipments/by-tracking/{tracking_number}",
        "/shipments/{shipment_id}/events",
        "/shipments/{shipment_id}/notification-preferences",
        "/shipments/{shipment_id}/notifications",
        "/webhooks/carrier",
        "/health",
        "/ready",
    } <= set(document["paths"])
