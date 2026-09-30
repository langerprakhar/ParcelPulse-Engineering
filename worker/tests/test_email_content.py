import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from parcelpulse_worker.email_content import NotificationContext, message_id_for, render_email
from parcelpulse_worker.senders import PermanentDeliveryError

SHIPMENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
NOTIFICATION_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def context(notification_type: str = "OUT_FOR_DELIVERY", **overrides: Any) -> NotificationContext:
    values: dict[str, Any] = {
        "notification_id": NOTIFICATION_ID,
        "notification_type": notification_type,
        "destination": "recipient@example.com",
        "shipment_id": SHIPMENT_ID,
        "tracking_number": "SC4F7K2M9Q1X",
        "carrier": "simcarrier",
        "event_at": datetime(2026, 9, 30, 14, 5, tzinfo=UTC),
        "location": {"facility": "Leeds Hub", "city": "Leeds", "region": "ENG", "country": "GB"},
        "description": "Loaded on delivery vehicle",
        "estimated_delivery_at": datetime(2026, 9, 30, 18, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return NotificationContext(**values)


def render(ctx: NotificationContext) -> Any:
    return render_email(
        ctx, sender="ParcelPulse <notifications@parcelpulse.local>", web_base_url="http://web/"
    )


@pytest.mark.parametrize(
    ("notification_type", "subject", "headline"),
    [
        (
            "OUT_FOR_DELIVERY",
            "Out for delivery: SC4F7K2M9Q1X",
            "Your parcel SC4F7K2M9Q1X is out for delivery.",
        ),
        ("DELIVERED", "Delivered: SC4F7K2M9Q1X", "Your parcel SC4F7K2M9Q1X has been delivered."),
        (
            "DELIVERY_EXCEPTION",
            "Delivery problem: SC4F7K2M9Q1X",
            "There is a problem with the delivery of your parcel SC4F7K2M9Q1X.",
        ),
    ],
)
def test_each_notification_type_has_its_own_subject_and_headline(
    notification_type: str, subject: str, headline: str
) -> None:
    message = render(context(notification_type))

    assert message["Subject"] == subject
    assert message.get_content().splitlines()[0] == headline


def test_message_is_addressed_and_identified() -> None:
    message = render(context())

    assert message["To"] == "recipient@example.com"
    assert message["From"] == "ParcelPulse <notifications@parcelpulse.local>"
    assert message["Message-ID"] == f"<{NOTIFICATION_ID}@notifications.parcelpulse>"
    assert message["X-ParcelPulse-Notification-Id"] == str(NOTIFICATION_ID)
    assert message["X-ParcelPulse-Notification-Type"] == "OUT_FOR_DELIVERY"
    assert message["X-ParcelPulse-Shipment-Id"] == str(SHIPMENT_ID)


def test_message_id_is_stable_for_a_notification() -> None:
    assert message_id_for(NOTIFICATION_ID) == message_id_for(NOTIFICATION_ID)
    assert message_id_for(NOTIFICATION_ID) != message_id_for(uuid.uuid4())


def test_body_describes_the_event_and_links_to_the_shipment() -> None:
    body = render(context()).get_content()

    assert "Status: Out for delivery" in body
    assert "When: 30 Sep 2026, 14:05 UTC" in body
    assert "Where: Leeds Hub, Leeds, ENG, GB" in body
    assert "Carrier: simcarrier" in body
    assert "Note: Loaded on delivery vehicle" in body
    assert "Estimated delivery: 30 Sep 2026, 18:00 UTC" in body
    assert f"Track it: http://web/shipments/{SHIPMENT_ID}" in body
    assert f"Change your preferences: http://web/shipments/{SHIPMENT_ID}/notifications" in body


def test_delivered_message_does_not_show_an_estimate() -> None:
    assert "Estimated delivery" not in render(context("DELIVERED")).get_content()


def test_missing_optional_details_are_left_out() -> None:
    body = render(
        context(location=None, description=None, estimated_delivery_at=None)
    ).get_content()

    assert "Where:" not in body
    assert "Note:" not in body
    assert "Estimated delivery" not in body
    assert "None" not in body


def test_partial_location_is_joined_without_gaps() -> None:
    body = render(context(location={"city": "Leeds", "country": "GB"})).get_content()
    assert "Where: Leeds, GB" in body


def test_event_time_is_shown_in_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    body = render(context(event_at=datetime(2026, 9, 30, 16, 5, tzinfo=plus_two))).get_content()
    assert "When: 30 Sep 2026, 14:05 UTC" in body


def test_unsupported_type_is_a_permanent_error() -> None:
    with pytest.raises(PermanentDeliveryError, match="unsupported notification type"):
        render(context("RETURNED"))


def test_destination_with_line_break_is_rejected() -> None:
    with pytest.raises(PermanentDeliveryError, match="line break"):
        render(context(destination="victim@example.com\nBcc: attacker@example.com"))
