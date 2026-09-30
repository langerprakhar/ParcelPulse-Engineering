"""The simulated carrier: shipments, their planned events, and ways to send them.

State is kept in memory. Restarting the simulator forgets every simulated
shipment, which is fine for a development tool.
"""

import json
import random
import secrets
import string
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from carrier_simulator.scenarios import DEFAULT_SCENARIO, SCENARIOS, Step
from carrier_simulator.sender import SendResult, WebhookSender

# Journeys are scheduled to end this long before the moment they are created.
JOURNEY_END_MARGIN = timedelta(hours=2)
TRACKING_ALPHABET = string.ascii_uppercase + string.digits

EventState = Literal["planned", "held", "sent"]


class SimulatorError(Exception):
    """The requested operation does not make sense in the shipment's current state."""


class UnknownShipmentError(SimulatorError):
    pass


class RegistrationError(SimulatorError):
    pass


@dataclass(slots=True)
class PlannedEvent:
    event_id: str
    step: Step
    occurred_at: datetime
    state: EventState = "planned"
    # The exact bytes sent for this event; reused for every redelivery.
    body: bytes | None = None


@dataclass(frozen=True, slots=True)
class Delivery:
    """One webhook delivery: the event, and every HTTP attempt made for it."""

    event_id: str
    event_type: str
    occurred_at: datetime
    # True when this event had already been delivered before.
    duplicate: bool
    send: SendResult


@dataclass(slots=True)
class SimulatedShipment:
    tracking_number: str
    scenario: str
    started_at: datetime
    events: list[PlannedEvent]
    registered: bool = False
    deliveries: list[Delivery] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def in_state(self, state: EventState) -> list[PlannedEvent]:
        return [event for event in self.events if event.state == state]


@dataclass(frozen=True, slots=True)
class BurstSummary:
    shipments: int
    events: int
    deliveries: int
    http_attempts: int
    undelivered: int
    results: dict[str, int]
    duration_seconds: float
    tracking_numbers: list[str]


Register = Callable[[str, str | None], None]


class Simulator:
    def __init__(
        self,
        sender: WebhookSender,
        *,
        carrier_code: str = "simcarrier",
        register: Register | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        rng: random.Random | None = None,
    ) -> None:
        self._sender = sender
        self._carrier_code = carrier_code
        self._register = register
        self._clock = clock
        self._rng = rng or random.Random()
        self._shipments: dict[str, SimulatedShipment] = {}
        self._lock = threading.Lock()

    # --- Shipments ----------------------------------------------------------

    def create_shipment(
        self,
        *,
        scenario: str = DEFAULT_SCENARIO,
        tracking_number: str | None = None,
        register: bool = False,
        notification_email: str | None = None,
    ) -> SimulatedShipment:
        steps = SCENARIOS.get(scenario)
        if steps is None:
            raise SimulatorError(
                f"unknown scenario '{scenario}'; choose one of {', '.join(sorted(SCENARIOS))}"
            )
        tracking_number = (tracking_number or self._new_tracking_number()).strip().upper()

        duration = timedelta(hours=max(step.offset_hours for step in steps))
        started_at = self._clock() - duration - JOURNEY_END_MARGIN
        shipment = SimulatedShipment(
            tracking_number=tracking_number,
            scenario=scenario,
            started_at=started_at,
            events=[
                PlannedEvent(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    step=step,
                    occurred_at=started_at + timedelta(hours=step.offset_hours),
                )
                for step in sorted(steps, key=lambda step: step.offset_hours)
            ],
        )

        with self._lock:
            if tracking_number in self._shipments:
                raise SimulatorError(f"shipment {tracking_number} already exists")
            self._shipments[tracking_number] = shipment

        if register:
            if self._register is None:
                raise RegistrationError("registration with ParcelPulse is not configured")
            self._register(tracking_number, notification_email)
            shipment.registered = True
        return shipment

    def get(self, tracking_number: str) -> SimulatedShipment:
        with self._lock:
            shipment = self._shipments.get(tracking_number.strip().upper())
        if shipment is None:
            raise UnknownShipmentError(f"no simulated shipment {tracking_number}")
        return shipment

    def all_shipments(self) -> list[SimulatedShipment]:
        with self._lock:
            return list(self._shipments.values())

    def reset(self) -> int:
        with self._lock:
            count = len(self._shipments)
            self._shipments.clear()
        return count

    def _new_tracking_number(self) -> str:
        return "SC" + "".join(secrets.choice(TRACKING_ALPHABET) for _ in range(10))

    # --- Sending events -----------------------------------------------------

    def advance(self, tracking_number: str, *, count: int = 1) -> list[Delivery]:
        """Send the next ``count`` planned events, in journey order."""
        shipment = self.get(tracking_number)
        with shipment.lock:
            planned = shipment.in_state("planned")
            if not planned:
                raise SimulatorError("no planned events left; the journey is complete")
            return [self._deliver(shipment, event) for event in planned[:count]]

    def hold(self, tracking_number: str, *, count: int = 1) -> list[PlannedEvent]:
        """Skip the next ``count`` planned events for now; they are sent late by release_held."""
        shipment = self.get(tracking_number)
        with shipment.lock:
            planned = shipment.in_state("planned")
            if not planned:
                raise SimulatorError("no planned events left to hold")
            held = planned[:count]
            for event in held:
                event.state = "held"
            return held

    def release_held(self, tracking_number: str) -> list[Delivery]:
        """Send every held event now: a delayed delivery of events that happened earlier."""
        shipment = self.get(tracking_number)
        with shipment.lock:
            held = shipment.in_state("held")
            if not held:
                raise SimulatorError("no held events to release")
            return [self._deliver(shipment, event) for event in held]

    def out_of_order(self, tracking_number: str) -> list[Delivery]:
        """Send the next two planned events in swapped order."""
        shipment = self.get(tracking_number)
        with shipment.lock:
            planned = shipment.in_state("planned")
            if len(planned) < 2:
                raise SimulatorError("need at least two planned events to send out of order")
            first, second = planned[0], planned[1]
            return [self._deliver(shipment, second), self._deliver(shipment, first)]

    def duplicate(
        self, tracking_number: str, *, event_id: str | None = None, count: int = 1
    ) -> list[Delivery]:
        """Redeliver an event that was already sent (the most recent one by default)."""
        shipment = self.get(tracking_number)
        with shipment.lock:
            if event_id is None:
                if not shipment.deliveries:
                    raise SimulatorError("no event has been sent yet")
                event_id = shipment.deliveries[-1].event_id
            event = next(
                (
                    candidate
                    for candidate in shipment.events
                    if candidate.event_id == event_id and candidate.state == "sent"
                ),
                None,
            )
            if event is None:
                raise SimulatorError(f"event {event_id} has not been sent for this shipment")
            return [self._deliver(shipment, event) for _ in range(count)]

    def exception(self, tracking_number: str) -> list[Delivery]:
        """Inject a delivery exception after the most recently sent event."""
        shipment = self.get(tracking_number)
        with shipment.lock:
            sent = shipment.in_state("sent")
            if not sent:
                raise SimulatorError("send at least one event before injecting an exception")
            latest = max(sent, key=lambda event: event.occurred_at)
            later = [event for event in shipment.events if event.occurred_at > latest.occurred_at]
            if later:
                gap = min(event.occurred_at for event in later) - latest.occurred_at
                occurred_at = latest.occurred_at + gap / 2
            else:
                occurred_at = latest.occurred_at + timedelta(minutes=30)
            injected = PlannedEvent(
                event_id=f"evt_{uuid.uuid4().hex}",
                step=Step(
                    "DELIVERY_EXCEPTION",
                    (occurred_at - shipment.started_at).total_seconds() / 3600,
                    latest.step.location,
                    "Delivery attempted, nobody available to receive the parcel",
                ),
                occurred_at=occurred_at,
            )
            shipment.events.append(injected)
            shipment.events.sort(key=lambda event: event.occurred_at)
            return [self._deliver(shipment, injected)]

    def lifecycle(
        self, tracking_number: str, *, shuffle: bool = False, duplicates: int = 0
    ) -> list[Delivery]:
        """Send every event not yet sent. Optionally shuffled, optionally each one repeated."""
        shipment = self.get(tracking_number)
        with shipment.lock:
            remaining = [event for event in shipment.events if event.state != "sent"]
            if not remaining:
                raise SimulatorError("every event has already been sent")
            if shuffle:
                self._rng.shuffle(remaining)
            deliveries: list[Delivery] = []
            for event in remaining:
                deliveries.append(self._deliver(shipment, event))
                deliveries.extend(self._deliver(shipment, event) for _ in range(duplicates))
            return deliveries

    def burst(
        self,
        *,
        shipments: int,
        scenario: str = DEFAULT_SCENARIO,
        register: bool = True,
        shuffle: bool = False,
        duplicates: int = 0,
        concurrency: int = 8,
    ) -> BurstSummary:
        """Create many shipments and play out all their journeys concurrently."""
        started = time.perf_counter()
        created = [
            self.create_shipment(scenario=scenario, register=register) for _ in range(shipments)
        ]

        def play(shipment: SimulatedShipment) -> list[Delivery]:
            return self.lifecycle(shipment.tracking_number, shuffle=shuffle, duplicates=duplicates)

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            deliveries = [delivery for batch in pool.map(play, created) for delivery in batch]

        results: Counter[str] = Counter(
            delivery.send.result or "NO_RESULT" for delivery in deliveries
        )
        return BurstSummary(
            shipments=len(created),
            events=sum(len(shipment.events) for shipment in created),
            deliveries=len(deliveries),
            http_attempts=sum(len(delivery.send.attempts) for delivery in deliveries),
            undelivered=sum(1 for delivery in deliveries if not delivery.send.delivered),
            results=dict(results),
            duration_seconds=round(time.perf_counter() - started, 3),
            tracking_numbers=[shipment.tracking_number for shipment in created],
        )

    # --- Internals ----------------------------------------------------------

    def _deliver(self, shipment: SimulatedShipment, event: PlannedEvent) -> Delivery:
        duplicate = event.state == "sent"
        if event.body is None:
            event.body = self._encode(shipment, event)
        send = self._sender.send(event.body)
        event.state = "sent"
        delivery = Delivery(
            event_id=event.event_id,
            event_type=event.step.event_type,
            occurred_at=event.occurred_at,
            duplicate=duplicate,
            send=send,
        )
        shipment.deliveries.append(delivery)
        return delivery

    def _encode(self, shipment: SimulatedShipment, event: PlannedEvent) -> bytes:
        payload: dict[str, Any] = {
            "provider": self._carrier_code,
            "event_id": event.event_id,
            "tracking_number": shipment.tracking_number,
            "event_type": event.step.event_type,
            "occurred_at": event.occurred_at.isoformat(),
            "location": event.step.location,
            "description": event.step.description,
        }
        if event.step.eta_offset_hours is not None:
            estimate = shipment.started_at + timedelta(hours=event.step.eta_offset_hours)
            payload["estimated_delivery_at"] = estimate.isoformat()
        return json.dumps(payload, separators=(",", ":")).encode()
