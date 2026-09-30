"""Shipment journeys the simulator can play out.

A scenario is an ordered list of steps. ``offset_hours`` positions each event
on the carrier's clock relative to the start of the journey; journeys are
scheduled to have finished shortly before "now", so every event the simulator
sends carries a realistic past timestamp however quickly it is sent.
"""

from dataclasses import dataclass

Location = dict[str, str]

ORIGIN: Location = {
    "facility": "Leeds Parcel Hub",
    "city": "Leeds",
    "region": "ENG",
    "country": "GB",
}
HUB: Location = {
    "facility": "Midlands Distribution Centre",
    "city": "Coventry",
    "region": "ENG",
    "country": "GB",
}
LOCAL: Location = {
    "facility": "Bristol Delivery Office",
    "city": "Bristol",
    "region": "ENG",
    "country": "GB",
}
DOORSTEP: Location = {"city": "Bristol", "region": "ENG", "country": "GB"}


@dataclass(frozen=True, slots=True)
class Step:
    event_type: str
    offset_hours: float
    location: Location
    description: str
    # The carrier's delivery estimate at this point in the journey, if it gives one.
    eta_offset_hours: float | None = None


_TO_LOCAL_DEPOT = [
    Step("LABEL_CREATED", 0, ORIGIN, "Shipping label created", eta_offset_hours=52),
    Step("IN_TRANSIT", 4, ORIGIN, "Collected and departed origin facility", eta_offset_hours=52),
    Step("AT_DISTRIBUTION_CENTER", 20, HUB, "Arrived at distribution centre"),
    Step("IN_TRANSIT", 28, HUB, "Departed distribution centre", eta_offset_hours=50),
    Step("AT_DISTRIBUTION_CENTER", 40, LOCAL, "Arrived at local delivery office"),
    Step("OUT_FOR_DELIVERY", 44, LOCAL, "Loaded on delivery vehicle", eta_offset_hours=50),
]

SCENARIOS: dict[str, list[Step]] = {
    # The parcel arrives without incident.
    "standard": [
        *_TO_LOCAL_DEPOT,
        Step("DELIVERED", 50, DOORSTEP, "Delivered, handed to resident"),
    ],
    # The first delivery attempt fails; the second succeeds the next day.
    "exception": [
        *_TO_LOCAL_DEPOT,
        Step(
            "DELIVERY_EXCEPTION",
            47,
            DOORSTEP,
            "Delivery attempted, nobody available to receive the parcel",
            eta_offset_hours=72,
        ),
        Step("OUT_FOR_DELIVERY", 68, LOCAL, "Loaded on delivery vehicle", eta_offset_hours=72),
        Step("DELIVERED", 72, DOORSTEP, "Delivered, handed to resident"),
    ],
    # The parcel cannot be delivered and goes back to the sender.
    "returned": [
        *_TO_LOCAL_DEPOT,
        Step("DELIVERY_EXCEPTION", 47, DOORSTEP, "Address could not be found"),
        Step("RETURNED", 96, ORIGIN, "Returned to sender"),
    ],
}

DEFAULT_SCENARIO = "standard"
