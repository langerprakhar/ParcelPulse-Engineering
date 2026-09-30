"""Deriving a shipment's current state from its carrier events.

The state is a pure function of the *set* of events known for a shipment. It
never depends on the order in which those events were delivered to us, so a
webhook that arrives hours late is recorded in the timeline without being able
to move the shipment backwards.

Ordering policy
---------------
1. Events are ordered by ``event_at`` (the carrier's clock), not ``received_at``.
2. The current status is the status implied by the event with the greatest
   ``event_at``.
3. Terminal statuses (DELIVERED, RETURNED) are sticky: once any terminal event
   exists, only terminal events are considered for the current status.
4. Ties on ``event_at`` are broken by status progression rank, then by
   ``received_at``, then by event id, so the result is deterministic.
5. The estimated delivery time is the one carried by the event with the
   greatest ``event_at`` among events that carry an estimate.

See docs/event-processing.md and ADR-003 for the reasoning.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from parcelpulse_api.domain.status import (
    PROGRESS_RANK,
    STATUS_FOR_EVENT,
    TERMINAL_STATUSES,
    EventType,
    ShipmentStatus,
)


@dataclass(frozen=True, slots=True)
class EventFacts:
    """The parts of a tracking event that decide shipment state."""

    id: uuid.UUID
    event_type: EventType
    event_at: datetime
    received_at: datetime
    estimated_delivery_at: datetime | None = None

    @property
    def status(self) -> ShipmentStatus:
        return STATUS_FOR_EVENT[self.event_type]


@dataclass(frozen=True, slots=True)
class ShipmentState:
    status: ShipmentStatus
    last_event_at: datetime | None
    estimated_delivery_at: datetime | None
    # The event the current status comes from; None while no event is known.
    deciding_event_id: uuid.UUID | None


def _precedence(event: EventFacts) -> tuple[datetime, int, datetime, str]:
    return (event.event_at, PROGRESS_RANK[event.status], event.received_at, str(event.id))


def derive_state(events: Iterable[EventFacts]) -> ShipmentState:
    known = list(events)
    if not known:
        return ShipmentState(
            status=ShipmentStatus.CREATED,
            last_event_at=None,
            estimated_delivery_at=None,
            deciding_event_id=None,
        )

    terminal = [event for event in known if event.status in TERMINAL_STATUSES]
    deciding = max(terminal or known, key=_precedence)

    with_estimate = [event for event in known if event.estimated_delivery_at is not None]
    estimate = max(with_estimate, key=_precedence).estimated_delivery_at if with_estimate else None

    return ShipmentState(
        status=deciding.status,
        last_event_at=max(event.event_at for event in known),
        estimated_delivery_at=estimate,
        deciding_event_id=deciding.id,
    )


def arrived_out_of_order(event: EventFacts, already_known: Iterable[EventFacts]) -> bool:
    """True when we had already received an event that happened after this one."""
    return any(other.event_at > event.event_at for other in already_known)
