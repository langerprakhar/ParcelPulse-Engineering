# ADR-004: Notification queue choice

- Status: Accepted
- Date: 2026-09-30

## Context

Sending an email can take seconds and can fail. It must not happen inside the
carrier webhook request, so notifications are delivered asynchronously by a
separate worker. We need a way to hand work from the API to the worker that

- needs little infrastructure (the stack already has PostgreSQL and Redis),
- can delay a message, for retries with backoff,
- runs in tests without external services, including on Windows development
  machines,
- does not have to be trusted for correctness, because the API's database
  transaction cannot include the queue.

## Decision

**Dramatiq with the Redis broker**, used as a wake-up mechanism on top of a
transactional outbox.

- The API writes the `notifications` row in the webhook transaction and
  publishes a message naming the row after commit.
- The message carries only the notification id and a correlation id.
- The worker claims the row in PostgreSQL before sending. The claim, not the
  message, decides whether an email goes out.
- Retry scheduling (attempt counter, next attempt time) is stored on the row.
  Dramatiq's delayed messages trigger the retry; Dramatiq's own retry
  middleware only covers errors that occur before the claim.
- A sweeper process re-publishes rows whose message was lost.
- The API publishes by constructing the message itself (queue name, actor
  name, arguments), so it does not import worker code. That contract is
  documented in `docs/notification-system.md` and tested on both sides.

## Alternatives considered

**RQ.** The simplest Redis queue. Its worker relies on `fork()` and does not
run on Windows, delayed jobs need its scheduler component to be running, and
its tests need Redis or a Redis fake rather than a built-in in-memory broker.
Rejected mainly for the test and local-development story.

**Celery.** Mature and featureful, but far more configuration surface than one
task needs, and its reliability settings (`acks_late`, visibility timeouts,
prefetch) take care to get right. Rejected as more than the problem requires.

**PostgreSQL only**: workers poll the outbox with
`SELECT ... FOR UPDATE SKIP LOCKED`, no broker at all. Attractive because it
removes the dual write entirely, and the sweeper already works this way. It
was not chosen as the primary path because polling trades latency against
load, and Redis is in the stack anyway. It remains the fallback: with Redis
gone, the sweeper's queries describe exactly what is outstanding.

**Kafka, RabbitMQ or a cloud queue.** More infrastructure to run for a
single, low-volume queue.

## Consequences

- Delivery is at-least-once at the queue level and exactly-once at the
  notification level for every failure except a worker crash between the mail
  server accepting a message and the row being marked `SENT`
  (see `docs/notification-system.md`).
- Losing Redis loses no notifications: rows stay `PENDING` and are
  re-published.
- The worker depends on the API's database schema. A change to the
  `notifications` table must be made in both components; the full-stack
  smoke test in `infra/` is what catches a mismatch.
- The queue and actor names are a cross-repository contract.
- The Dramatiq command-line worker runs in Linux containers. Tests use
  Dramatiq's in-memory `StubBroker` with a real worker thread pool and run on
  any platform.
- Two processes to operate: the worker and the sweeper.
