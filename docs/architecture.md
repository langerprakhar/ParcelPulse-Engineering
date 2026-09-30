# Architecture

ParcelPulse tracks parcels. Users register a tracking number, carriers report
events by webhook, ParcelPulse keeps the shipment's timeline and current
status, and notifies the user at the moments that matter.

## System overview

```
                         Browser
                            │ HTML, form posts
                            ▼
                    ┌───────────────┐
                    │ parcelpulse-  │  Next.js server (renders pages,
                    │ web           │  runs Server Actions)
                    └───────┬───────┘
                            │ HTTP/JSON
                            ▼
 Carrier ── signed ──▶ ┌───────────────┐ ── publish ──▶ ┌────────┐
 (locally: the         │ parcelpulse-  │                │ Redis  │
  carrier simulator)   │ api           │                └───┬────┘
      webhooks         └───────┬───────┘                    │ consume
                               │ SQL                        ▼
                               ▼                    ┌───────────────┐
                        ┌─────────────┐ ◀── SQL ─── │ parcelpulse-  │ ── SMTP ──▶ mail server
                        │ PostgreSQL  │             │ worker        │            (locally: Mailpit)
                        └─────────────┘ ◀── SQL ─── │ + sweeper     │
                                                    └───────────────┘
```

## Components

| Component          | Repository                          | Technology                                   | Responsibility                                                                  |
| ------------------ | ----------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------- |
| Web dashboard      | `parcelpulse-web`                   | Next.js 16, React 19, TypeScript             | Search, shipment list, timeline, notification preferences, developer tools      |
| API                | `parcelpulse-api`                   | Python 3.12, FastAPI, SQLAlchemy 2, Alembic  | Owns the data and the schema; webhook ingestion; state derivation; notification outbox |
| Worker             | `parcelpulse-worker`                | Python 3.12, Dramatiq                        | Delivers notifications by email; retries                                        |
| Sweeper            | `parcelpulse-worker` (same image)   | Python 3.12                                  | Re-publishes lost queue messages; releases abandoned sends                      |
| Carrier simulator  | `parcelpulse-infra/carrier-simulator` | Python 3.12, FastAPI                       | Development stand-in for a carrier; sends signed webhooks                       |
| PostgreSQL 17      | image                               |                                              | System of record                                                                |
| Redis 7            | image                               |                                              | Message broker between API and worker                                           |
| Mailpit            | image                               |                                              | Development mail sink; nothing leaves the machine                               |

This repository (`parcelpulse-infra`) holds the Compose stack, the carrier
simulator, the smoke and load tests, the Slack app configuration and the
system-level documentation.

## Main flows

### Registering a shipment

1. The user submits a tracking number, carrier and optional email in the web
   dashboard. A Server Action calls `POST /shipments`.
2. The API stores the shipment with status `CREATED` and, if an email was
   given, its notification preference. The pair `(carrier, tracking_number)`
   is unique.

### A carrier event

1. The carrier calls `POST /webhooks/carrier` with a signed JSON body.
2. The API verifies the signature and validates the payload.
3. In one transaction it stores the event (unless it is a duplicate),
   recomputes the shipment's state from all of its events, writes a
   notification row if one is owed, and writes an audit receipt.
4. After commit it publishes one message per notification to Redis.
5. It answers 200 with the result: `PROCESSED`, `DUPLICATE`,
   `DUPLICATE_PAYLOAD_MISMATCH` or `UNKNOWN_SHIPMENT`.

### A notification

1. The worker receives the message and claims the notification row.
2. It renders the email and sends it over SMTP.
3. It records `SENT`, schedules a retry, or marks the notification `FAILED`.

### Viewing a shipment

The web server fetches the shipment, its timeline and its preferences from the
API while rendering the page. The page refreshes that data every ten seconds.

## Key properties and where they are decided

| Property                                                     | Mechanism                                                                              | Document                                                         |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| A redelivered webhook changes nothing                        | Unique `(provider, provider_event_id)`; `INSERT ... ON CONFLICT DO NOTHING`; one transaction | `parcelpulse-api/docs/webhook-idempotency.md`, ADR-002      |
| A late event cannot move a shipment backwards                | State derived from all events by carrier time; terminal statuses sticky                | `parcelpulse-api/docs/event-processing.md`, ADR-003              |
| Carrier time and receipt time are both kept                  | `event_at` and `received_at` on every event                                            | `parcelpulse-api/docs/event-processing.md`                       |
| A notification is sent once                                  | Transactional outbox; atomic claim in the worker; queue messages are only hints        | `parcelpulse-worker/docs/notification-system.md`, ADR-004        |
| Webhooks are authentic                                       | HMAC-SHA256 over timestamp and body, with a tolerance window                           | `parcelpulse-api/docs/api-spec.md`                               |

## Data

All persistent data is in one PostgreSQL database, owned and migrated by the
API.

| Table                      | Written by      | Read by          |
| -------------------------- | --------------- | ---------------- |
| `shipments`                | API             | API, worker      |
| `tracking_events`          | API             | API, worker      |
| `webhook_receipts`         | API             | API              |
| `notification_preferences` | API             | API              |
| `notifications`            | API (insert), worker (status) | API, worker |

Redis holds only queue messages. Losing it loses no notifications: the rows
stay `PENDING` in PostgreSQL and the sweeper re-publishes them. The carrier
simulator keeps its state in memory.

## Contracts between repositories

| Contract                  | Producer            | Consumer             | Defined in                                          |
| ------------------------- | ------------------- | -------------------- | --------------------------------------------------- |
| REST API                  | API                 | web                  | OpenAPI; `parcelpulse-api/docs/api-spec.md`; mirrored in `parcelpulse-web/src/lib/types.ts` |
| Carrier webhook           | carrier / simulator | API                  | `parcelpulse-api/docs/api-spec.md`                  |
| Notification queue message | API                | worker               | `parcelpulse-worker/docs/notification-system.md`    |
| Database schema           | API (Alembic)       | worker               | API migrations; mirrored in `parcelpulse-worker/src/parcelpulse_worker/db.py` |

The last two are shared without shared code. Each side has tests for its own
half, and the full-stack smoke test in this repository exercises them
together.

## Cross-cutting concerns

**Correlation IDs.** The API assigns or accepts an ID for every request,
returns it in `X-Correlation-ID`, stores it on the event, receipt and
notification, and passes it to the worker, whose logs carry it too. One ID
follows a webhook from receipt to email.

**Logging.** API and worker write one JSON object per line to stdout. Values
under sensitive-looking keys are redacted.

**Health.**

| Service           | Liveness        | Readiness                                     |
| ----------------- | --------------- | --------------------------------------------- |
| API               | `GET /health`   | `GET /ready` (PostgreSQL and Redis)           |
| Web               | `GET /api/health` | `GET /api/ready` (API reachable and ready)  |
| Worker, sweeper   | container healthcheck: `python -m parcelpulse_worker.healthcheck` (PostgreSQL and Redis) | |
| Carrier simulator | `GET /health`   |                                               |

**Metrics.** The API exposes Prometheus metrics at `GET /metrics`. Nothing
scrapes them yet.

**Security.** No secrets in source control; configuration comes from
environment variables. Webhooks are signed. Development endpoints (`/dev` on
the API, `/dev` on the web) exist only when explicitly enabled, and the API
refuses to enable them in production. There is **no user authentication** in
v0.1: the dashboard and the API's shipment endpoints are open to whoever can
reach them.

## What is deliberately not here

No Kubernetes, service mesh, message bus beyond one Redis queue, search
engine, or caching layer. See
[adr/ADR-001-service-architecture.md](adr/ADR-001-service-architecture.md).
