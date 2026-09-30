# Webhook idempotency

Carriers retry webhooks: on timeouts, on 5xx responses, and sometimes for no
visible reason. `POST /webhooks/carrier` can receive the same event any number
of times, concurrently, and must behave as if it had received it once.

## The guarantee

For a given `(provider, event_id)`:

- at most one `tracking_events` row exists;
- the shipment's state reflects the event exactly once;
- at most one notification per destination is created;
- every delivery attempt is answered with HTTP 200 and leaves a
  `webhook_receipts` row, so retries stop and the history is auditable.

## How it works

**The idempotency key** is the carrier's event id, scoped to the carrier:
the unique constraint `uq_tracking_events_provider_event_id` on
`tracking_events (provider, provider_event_id)`.

**One transaction per delivery.** The event, the shipment update, the
notification outbox row and the receipt are written in a single transaction
(`ingest_carrier_event`). Either all of them commit or none do.

**The insert is the check.** The event is written with

```sql
INSERT INTO tracking_events (...) VALUES (...)
ON CONFLICT ON CONSTRAINT uq_tracking_events_provider_event_id DO NOTHING
RETURNING id
```

If a row comes back, the event is new and processing continues. If not, it is
a duplicate. There is no separate "does it exist?" query that could race with
another delivery, and no exception to catch and interpret.

**Duplicates take a different, side-effect-free path.** A duplicate writes a
receipt that points at the original event and returns. It does not touch the
shipment, does not plan notifications and does not publish to the queue.

**Concurrent deliveries are serialised per shipment.** The transaction locks
the shipment row first, so two deliveries for the same shipment never
interleave. Even without that lock, `ON CONFLICT` makes the second insert wait
for the first transaction and then report a conflict.

## Why this is more than catching an integrity error

Storing the event once is only part of the problem. The cases that matter:

| Case                                                        | What happens                                                                                   |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Retry after a **successful** first delivery                 | Conflict on insert; receipt `DUPLICATE`; nothing else changes                                   |
| Retry after the first delivery **failed before commit**     | Nothing was written, so the retry is processed as a new event. It is not mistaken for a duplicate |
| Two deliveries **at the same time**                         | One inserts, the other conflicts; exactly one event, one state change, one notification         |
| Retry of an **old** event after later events were processed | Conflict on insert; the shipment is not rewound                                                 |
| Commit succeeds but **publishing** the notification fails   | The notification row is already durable as `PENDING`; the worker's sweeper publishes it later   |
| Same event id, **different body**                           | Receipt `DUPLICATE_PAYLOAD_MISMATCH`, a warning in the log; the stored event is kept unchanged  |

The notification is the part that a naive implementation gets wrong. Here the
notification row is inserted in the same transaction as the event, and only
for a newly inserted event, so "event stored once" implies "notification
created at most once". The queue message is published after commit and is only
a wake-up call; the worker's claim on the row decides whether anything is sent
(see `worker/docs/notification-system.md`).

## Payload fingerprint

`payload_hash` is the SHA-256 of the JSON body with sorted keys and no
insignificant whitespace. A retry that re-serialises the same event (different
key order or spacing) has the same fingerprint and is a plain `DUPLICATE`.

## Results

`result` in the response body and in `webhook_receipts`:

| Result                       | `duplicate` | Meaning                                                       |
| ---------------------------- | ----------- | ------------------------------------------------------------- |
| `PROCESSED`                  | false       | New event stored and applied                                  |
| `DUPLICATE`                  | true        | Event already stored; nothing changed                         |
| `DUPLICATE_PAYLOAD_MISMATCH` | true        | Event id already stored with different content; original kept |
| `UNKNOWN_SHIPMENT`           | false       | No shipment with that carrier and tracking number; ignored    |

`UNKNOWN_SHIPMENT` deliveries are not deduplicated (there is no event to
conflict with); each leaves a receipt.

## Tests

`tests/integration/test_webhook_idempotency.py` covers each row of the table
above against a real PostgreSQL, including twelve concurrent deliveries of one
event and fifteen concurrent deliveries of five events for one shipment.
`tests/integration/test_notifications.py` covers the notification side.

## Inspecting receipts

With `ENABLE_DEV_ENDPOINTS=true` (never in production):

```
GET /dev/webhook-receipts?provider_event_id=<carrier event id>
```

## Known limitations

- `webhook_receipts` grows without bound; there is no retention job yet.
- A carrier that reuses event ids across genuinely different events will have
  the later ones ignored (reported as `DUPLICATE_PAYLOAD_MISMATCH`).
- One shared signing secret for all carriers.
