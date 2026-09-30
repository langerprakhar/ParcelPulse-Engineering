"""Shipment statuses and the carrier event types that produce them."""

from enum import StrEnum


class ShipmentStatus(StrEnum):
    # Registered in ParcelPulse; no carrier event seen yet.
    CREATED = "CREATED"
    LABEL_CREATED = "LABEL_CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    AT_DISTRIBUTION_CENTER = "AT_DISTRIBUTION_CENTER"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELIVERY_EXCEPTION = "DELIVERY_EXCEPTION"
    RETURNED = "RETURNED"


class EventType(StrEnum):
    """What a carrier reports. Each event type implies exactly one shipment status."""

    LABEL_CREATED = "LABEL_CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    AT_DISTRIBUTION_CENTER = "AT_DISTRIBUTION_CENTER"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    DELIVERY_EXCEPTION = "DELIVERY_EXCEPTION"
    RETURNED = "RETURNED"


STATUS_FOR_EVENT: dict[EventType, ShipmentStatus] = {
    event_type: ShipmentStatus(event_type.value) for event_type in EventType
}

# The parcel's journey is over; later non-terminal scans cannot reopen it.
TERMINAL_STATUSES: frozenset[ShipmentStatus] = frozenset(
    {ShipmentStatus.DELIVERED, ShipmentStatus.RETURNED}
)

# Used only to break ties between events that carry the same carrier timestamp.
PROGRESS_RANK: dict[ShipmentStatus, int] = {
    ShipmentStatus.CREATED: 0,
    ShipmentStatus.LABEL_CREATED: 1,
    ShipmentStatus.IN_TRANSIT: 2,
    ShipmentStatus.AT_DISTRIBUTION_CENTER: 3,
    ShipmentStatus.OUT_FOR_DELIVERY: 4,
    ShipmentStatus.DELIVERY_EXCEPTION: 5,
    ShipmentStatus.DELIVERED: 6,
    ShipmentStatus.RETURNED: 7,
}
