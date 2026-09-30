# ADR-002: Webhook idempotency strategy

- Status: Accepted
- Date: 2026-09-30

## Context

Carriers deliver tracking events by webhook and retry them. The same event can
arrive several times, minutes apart or simultaneously. Each event may change a
shipment's status and may cause a notification to a customer. Processing an
event twice must not duplicate the event, change the shipment twice, or send a
second notification.

Every carrier event has a carrier-assigned id (`event_id`).

## Decision

1. **Key.** `(provider, provider_event_id)` identifies an event. A unique
   constraint on `tracking_events` enforces it in PostgreSQL.
2. **Atomic check-and-write.** The event is inserted with
   `INSERT ... ON CONFLICT DO NOTHING RETURNING id`. The presence of a returned
   row is the only definition of "new event".
3. **One transaction.** The event, the derived shipment state, the notification
   outbox row and an audit receipt commit together.
4. **Duplicates have no side effects** beyond an audit receipt, and are
   answered with HTTP 200 and `result: DUPLICATE`.
5. **Notifications use a transactional outbox.** The API never calls the mail
   system or relies on the queue for correctness; it writes a row that the
   worker later claims.
6. **A reused event id with different content keeps the first version** and is
   reported as `DUPLICATE_PAYLOAD_MISMATCH`.

## Alternatives considered

**Catch the unique-violation error.** Insert normally and treat
`IntegrityError` as "duplicate". It aborts the surrounding transaction in
PostgreSQL, which forces savepoints around the insert, and it leaves the rest
of the workflow (state update, notification) to be made idempotent separately.
Rejected: easy to get subtly wrong.

**Deduplicate in Redis** with `SET NX` on the event id and a TTL. Fast, but the
marker and the database write are not atomic: a crash between them either
drops an event (marker set, nothing stored) or admits a duplicate (TTL
expired). Rejected for a correctness property.

**A separate idempotency-key table** written before processing. Equivalent to
the unique constraint on the event table itself, with one more table to keep
consistent. Rejected as unnecessary.

**Compare payload hashes instead of event ids.** Carriers re-serialise retries
and occasionally enrich them, so identical events would not always hash the
same. Rejected as the key; kept as a diagnostic (`payload_hash`).

## Consequences

- Correctness rests on PostgreSQL constraints and transactions, not on
  application-level locking or on the queue.
- Every delivery costs a database transaction, including duplicates.
- The receipts table records all attempts and needs a retention policy.
- A carrier that does not provide stable event ids cannot be integrated without
  deriving a key for it.
- The worker must treat queue messages as hints, because the queue is outside
  the transaction (see ADR-004 in `worker/docs/adr/`).

Details and the test matrix: [../webhook-idempotency.md](../webhook-idempotency.md).
