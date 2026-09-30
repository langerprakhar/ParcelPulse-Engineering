"""Shipment statuses."""

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
