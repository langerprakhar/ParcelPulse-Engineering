"""Turning a notification into an email message."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

from parcelpulse_worker.senders import PermanentDeliveryError


@dataclass(frozen=True, slots=True)
class NotificationContext:
    """Everything needed to write the message for one notification."""

    notification_id: uuid.UUID
    notification_type: str
    destination: str
    shipment_id: uuid.UUID
    tracking_number: str
    carrier: str
    event_at: datetime
    location: dict[str, Any] | None
    description: str | None
    estimated_delivery_at: datetime | None


@dataclass(frozen=True, slots=True)
class _Template:
    subject: str
    headline: str
    status: str
    show_estimate: bool


_TEMPLATES: dict[str, _Template] = {
    "OUT_FOR_DELIVERY": _Template(
        subject="Out for delivery: {tracking_number}",
        headline="Your parcel {tracking_number} is out for delivery.",
        status="Out for delivery",
        show_estimate=True,
    ),
    "DELIVERED": _Template(
        subject="Delivered: {tracking_number}",
        headline="Your parcel {tracking_number} has been delivered.",
        status="Delivered",
        show_estimate=False,
    ),
    "DELIVERY_EXCEPTION": _Template(
        subject="Delivery problem: {tracking_number}",
        headline="There is a problem with the delivery of your parcel {tracking_number}.",
        status="Delivery exception",
        show_estimate=True,
    ),
}


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _format_location(location: dict[str, Any] | None) -> str | None:
    if not location:
        return None
    parts = [location.get(key) for key in ("facility", "city", "region", "country")]
    text = ", ".join(str(part) for part in parts if part)
    return text or None


def message_id_for(notification_id: uuid.UUID) -> str:
    """Stable per notification, so a receiving system can drop a repeated send."""
    return f"<{notification_id}@notifications.parcelpulse>"


def render_email(context: NotificationContext, *, sender: str, web_base_url: str) -> EmailMessage:
    template = _TEMPLATES.get(context.notification_type)
    if template is None:
        raise PermanentDeliveryError(f"unsupported notification type '{context.notification_type}'")
    if "\n" in context.destination or "\r" in context.destination:
        raise PermanentDeliveryError("destination contains a line break")

    shipment_url = f"{web_base_url.rstrip('/')}/shipments/{context.shipment_id}"
    details = [
        ("Status", template.status),
        ("When", _format_time(context.event_at)),
        ("Where", _format_location(context.location)),
        ("Carrier", context.carrier),
        ("Note", context.description),
    ]
    if template.show_estimate and context.estimated_delivery_at is not None:
        details.append(("Estimated delivery", _format_time(context.estimated_delivery_at)))

    lines = [template.headline.format(tracking_number=context.tracking_number), ""]
    lines += [f"{label}: {value}" for label, value in details if value]
    lines += [
        "",
        f"Track it: {shipment_url}",
        "",
        "You are receiving this because notifications are enabled for this shipment.",
        f"Change your preferences: {shipment_url}/notifications",
    ]

    message = EmailMessage()
    message["From"] = sender
    message["To"] = context.destination
    message["Subject"] = template.subject.format(tracking_number=context.tracking_number)
    message["Message-ID"] = message_id_for(context.notification_id)
    message["X-ParcelPulse-Notification-Id"] = str(context.notification_id)
    message["X-ParcelPulse-Notification-Type"] = context.notification_type
    message["X-ParcelPulse-Shipment-Id"] = str(context.shipment_id)
    message.set_content("\n".join(lines) + "\n")
    return message
