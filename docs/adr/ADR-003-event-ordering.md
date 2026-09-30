# ADR-003: Event ordering semantics

- Status: Accepted
- Date: 2026-09-30

## Context

Carrier events do not arrive in the order they happened. Scans are uploaded in
batches, failed webhook deliveries are retried later, and some facilities
report hours late. If the shipment's status simply followed the most recently
*received* event, a late "arrived at hub" scan would move a parcel that is
already out for delivery back to the hub, and customers would be told the wrong
thing.

Each event has the carrier's own timestamp (`occurred_at`), which we store as
`event_at`, and our receipt time, `received_at`.

## Decision

The shipment's current state is **derived from the full set of its events**,
using event semantics and `event_at`, never arrival order:

1. The current status comes from the event with the greatest `event_at`.
2. `DELIVERED` and `RETURNED` are terminal and sticky: once one exists, only
   terminal events can decide the status.
3. Ties on `event_at` are broken by a fixed status progression rank, then by
   `received_at`, then by event id.
4. The delivery estimate is the one carried by the latest event (by `event_at`)
   that has one.
5. `received_at` is stored on every event and never used to decide the status
   except as a tie-break.
6. The state is recomputed from all events each time an event is stored.
7. Events dated more than one hour in the future are rejected.

The rules live in one pure function, `domain/state.py:derive_state`, with no
database access.

## Alternatives considered

**Last received wins.** Simplest, and wrong whenever events arrive late.

**A strict state machine with allowed transitions** (for example
`IN_TRANSIT -> OUT_FOR_DELIVERY -> DELIVERED`), rejecting or ignoring events
that are not a legal next step. Real journeys are not that regular: parcels
alternate between transit and hubs, exceptions are followed by new attempts,
and scans are skipped. A transition table would either reject valid data or
grow into a list of special cases, and it would still depend on arrival order.

**Incremental update**: keep the status and apply each event only if its
`event_at` is newer than the stored `last_event_at`. Cheaper per event, but the
stored state becomes something that can drift from the events, and the
terminal and tie-break rules have to be re-implemented as comparisons against
partial state.

**Trust carrier sequence numbers.** Not every carrier provides them.

## Consequences

- Any arrival order of the same events yields the same state, which makes the
  behaviour testable exhaustively (the unit tests try every permutation).
- Late events are visible: they are stored, shown in the timeline at their
  carrier-time position and flagged `arrived_out_of_order`.
- The design depends on carrier clocks being roughly right. A timestamp far in
  the future is rejected; one wrongly in the past is merely ordered early.
- A terminal status cannot be reversed by a later event. Correcting a wrong
  `DELIVERED` needs a manual process that does not exist yet.
- Reading all events of a shipment on every ingestion is O(events per
  shipment). That is tens of rows and an indexed lookup.
- Notifications follow from this decision: an event notifies only if it became
  the current status when ingested, so late history does not notify.

Details: [../event-processing.md](../event-processing.md).
