# Event processing

How a carrier event becomes shipment state. The code is in
`src/parcelpulse_api/domain/` (pure rules) and
`src/parcelpulse_api/services/webhooks.py` (persistence).

## Two clocks

Every tracking event carries two timestamps and both are stored:

| Field         | Meaning                                              | Source                     |
| ------------- | ---------------------------------------------------- | -------------------------- |
| `event_at`    | When it happened, by the carrier's clock             | `occurred_at` in the webhook |
| `received_at` | When ParcelPulse received the webhook                | The API's clock            |

They differ routinely. Carriers batch uploads, retry failed deliveries and
back-fill scans, so an event can arrive hours after a later one.

## Ordering policy

**Shipment state is a function of the set of events known for the shipment. It
does not depend on the order in which they were received.** The function is
`derive_state` in `domain/state.py`:

1. Events are ordered by `event_at`.
2. The current status is the status implied by the event with the greatest
   `event_at`.
3. `DELIVERED` and `RETURNED` are **terminal and sticky**. Once a terminal event
   exists, only terminal events are considered for the current status; among
   several, the one with the greatest `event_at` wins.
4. Ties on `event_at` are broken by status progression rank
   (`LABEL_CREATED < IN_TRANSIT < AT_DISTRIBUTION_CENTER < OUT_FOR_DELIVERY <
   DELIVERY_EXCEPTION < DELIVERED < RETURNED`), then `received_at`, then event
   id. The result is deterministic.
5. `estimated_delivery_at` is the estimate carried by the event with the
   greatest `event_at` among the events that carry one. A newer event without
   an estimate leaves the previous estimate in force.
6. `last_event_at` is the greatest `event_at` of any event, including events
   that did not decide the status.

Consequences:

- A delayed historical event is added to the timeline at its carrier-time
  position and cannot move the shipment backwards.
- The same events delivered in any order produce the same shipment state. A
  unit test checks every permutation of a full journey.
- A delivery exception is recoverable: a later `OUT_FOR_DELIVERY` or
  `DELIVERED` replaces it.
- A stray non-terminal scan dated after `DELIVERED` is recorded and advances
  `last_event_at`, but the shipment stays `DELIVERED`.

## Statuses

`CREATED` is the status of a shipment that is registered but has no events.
Every other status is produced by the carrier event type of the same name.

| Status                   | Terminal | Notifies |
| ------------------------ | -------- | -------- |
| `CREATED`                | no       | no       |
| `LABEL_CREATED`          | no       | no       |
| `IN_TRANSIT`             | no       | no       |
| `AT_DISTRIBUTION_CENTER` | no       | no       |
| `OUT_FOR_DELIVERY`       | no       | yes      |
| `DELIVERY_EXCEPTION`     | no       | yes      |
| `DELIVERED`              | yes      | yes      |
| `RETURNED`               | yes      | no       |

## Ingestion, step by step

For one authenticated, valid webhook, inside one database transaction:

1. Reject the event if `occurred_at` is more than
   `WEBHOOK_MAX_FUTURE_SKEW_SECONDS` (default one hour) in the future. A wrong
   carrier clock must not be able to pin a shipment's status.
2. Lock the shipment row (`SELECT ... FOR UPDATE`) by carrier and tracking
   number. Deliveries for one shipment are processed one at a time. If no such
   shipment exists, write a receipt with result `UNKNOWN_SHIPMENT` and stop.
3. Read the shipment's existing events and derive the state that would result
   from adding the new one.
4. Insert the event with `ON CONFLICT DO NOTHING` on
   `(provider, provider_event_id)`. If nothing was inserted the delivery is a
   duplicate: see [webhook-idempotency.md](webhook-idempotency.md).
5. Update the shipment's `current_status`, `last_event_at` and
   `estimated_delivery_at` from the derived state.
6. Write a notification to the outbox if the event owes one (next section).
7. Write the `webhook_receipts` row.

After the commit, the API publishes one queue message per notification.

The state is recomputed from all of the shipment's events on every ingestion.
A shipment has tens of events, so this is cheap, and it means there is no
incremental state that could drift from the events.

### Processing metadata

Each stored event records what happened when it was ingested:

| Column                 | Meaning                                                      |
| ---------------------- | ------------------------------------------------------------ |
| `arrived_out_of_order` | An event with a later `event_at` had already been received   |
| `changed_status`       | Ingesting it changed the shipment's current status           |
| `status_after`         | The shipment's status after ingesting it                     |
| `correlation_id`       | The correlation ID of the webhook request                    |

## When an event owes a notification

A newly stored event creates a notification only if all of these hold:

1. Its type is `OUT_FOR_DELIVERY`, `DELIVERED` or `DELIVERY_EXCEPTION`.
2. It **became the shipment's current status** when it was ingested.
3. The shipment has a notification email and that notification type is enabled.

Rule 2 keeps history quiet. An `OUT_FOR_DELIVERY` that arrives after the parcel
was delivered joins the timeline, but nobody is told the parcel is out for
delivery. A second `DELIVERED` event with a different event id does not change
the status and therefore does not notify again.

## Timeline

`GET /shipments/{id}/events` returns events ordered by `event_at`, then
`received_at`, then id. `order=desc` reverses it. Rows are never updated or
deleted after they are written.

## Known limitations

- A terminal status cannot be undone by a later event. A carrier correcting a
  wrong `DELIVERED` needs manual intervention today.
- Two different carrier events with the same `event_at` and type are both
  stored; the later-received one decides ties.
- The estimate is whatever the carrier last said. ParcelPulse does not compute
  one of its own.
