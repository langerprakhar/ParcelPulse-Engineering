# parcelpulse-api

HTTP API for ParcelPulse, a package tracking and delivery notification platform.

This directory is the former `parcelpulse-api` repository, imported with its
commit history into the ParcelPulse engineering repository. Run the commands
below from `api/`.

This service owns the data. It registers shipments, ingests carrier webhook
events, derives each shipment's current status from its events, decides which
notifications are owed, and serves all of it to the web dashboard.

| Concern                    | Where                                         | Doc                                                        |
| -------------------------- | --------------------------------------------- | ---------------------------------------------------------- |
| Endpoints, errors, webhook contract | `src/parcelpulse_api/routers/`       | [docs/api-spec.md](docs/api-spec.md)                       |
| Event ordering and state   | `src/parcelpulse_api/domain/`                 | [docs/event-processing.md](docs/event-processing.md)       |
| Duplicate webhooks         | `src/parcelpulse_api/services/webhooks.py`    | [docs/webhook-idempotency.md](docs/webhook-idempotency.md) |
| Notification outbox        | `src/parcelpulse_api/services/notifications.py`, `queue.py` | [../worker/docs/notification-system.md](../worker/docs/notification-system.md) |
| Decisions                  |                                               | [ADR-002](docs/adr/ADR-002-webhook-idempotency.md), [ADR-003](docs/adr/ADR-003-event-ordering.md) |

System-level documentation (architecture, local development, release process)
lives in [`docs/`](../docs/) at the repository root.

## Requirements

- Python 3.12
- PostgreSQL 17 and Redis 7 (disposable ones are provided through Docker for tests)

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Configuration is read from environment variables; `.env.example` lists every
one. `WEBHOOK_SIGNING_SECRET` has no default and must be set.

## Database

The schema is managed with Alembic. `DATABASE_URL` selects the database.

```powershell
alembic upgrade head      # create or update the schema
alembic check             # fail if the models and the schema have drifted apart
alembic downgrade -1      # undo the latest revision
```

| Table                      | Holds                                                                     |
| -------------------------- | ------------------------------------------------------------------------- |
| `shipments`                | One row per tracked parcel; `current_status` is derived from its events   |
| `tracking_events`          | Immutable carrier events; unique on `(provider, provider_event_id)`       |
| `webhook_receipts`         | One row per webhook delivery attempt, including duplicates                |
| `notification_preferences` | Email address and enabled notification types per shipment                 |
| `notifications`            | Outbox: written here, delivered by parcelpulse-worker                     |

## Run

The usual way to run the API is the full stack in `infra/`
(`docker compose up --build`). To run it directly against that stack's
PostgreSQL and Redis:

```powershell
alembic upgrade head
uvicorn parcelpulse_api.main:create_app --factory --reload --port 8000
```

- Liveness: `GET http://localhost:8000/health`
- Readiness: `GET http://localhost:8000/ready`
- OpenAPI: `http://localhost:8000/docs`
- Metrics: `GET http://localhost:8000/metrics`

## Tests

Unit tests need nothing but Python. Integration tests need PostgreSQL and
Redis; they rebuild the schema from zero with Alembic at the start of every run
and empty all tables before each test.

```powershell
docker compose -f docker-compose.dev.yml up -d --wait   # PostgreSQL :25432, Redis :26379
pytest tests/unit
pytest tests/integration
docker compose -f docker-compose.dev.yml down
```

| Suite                                           | What it covers                                                      |
| ----------------------------------------------- | ------------------------------------------------------------------- |
| `tests/unit/test_state_derivation.py`           | The ordering policy, including every arrival permutation of a journey |
| `tests/unit/test_signature.py`                  | Webhook signature verification                                      |
| `tests/integration/test_shipments_api.py`       | Registration, lookup, pagination, concurrent registration           |
| `tests/integration/test_webhook_ingestion.py`   | Authentication, validation and the effects of one delivery          |
| `tests/integration/test_webhook_idempotency.py` | Duplicate, concurrent and failed-then-retried deliveries            |
| `tests/integration/test_event_ordering.py`      | Delayed and out-of-order events through the HTTP API                |
| `tests/integration/test_timeline.py`            | Timeline ordering and pagination                                    |
| `tests/integration/test_notifications.py`       | Which events owe a notification, and exactly how many               |
| `tests/integration/test_queue_publisher.py`     | The Redis message contract with the worker                          |
| `tests/integration/test_migrations.py`          | Schema from zero, model/migration drift, downgrade and upgrade      |
| `tests/integration/test_operations.py`          | Readiness, metrics, development endpoints, OpenAPI                  |

Set `TEST_DATABASE_URL` / `TEST_REDIS_URL` to use other instances. The database
name must end in `_test`, because the test run drops and recreates the `public`
schema.

## Checks

```powershell
ruff check .
ruff format --check .
mypy
```

CI (`.github/workflows/api-ci.yml` at the repository root) runs these, the unit
tests, one job per integration suite, a migration sanity job and the Docker
build.

## Observability

- Logs are one JSON object per line and include the request's correlation ID.
  Values logged under keys that look sensitive (`secret`, `token`, `password`,
  `signature`, ...) are redacted.
- `GET /metrics` exposes request counts and durations by route template,
  webhook results, out-of-order events, planned notifications and publish
  failures.

## Dependencies

Direct dependencies are pinned in `pyproject.toml`. `constraints.txt` pins the
full resolved set for Linux and is used by the Docker image and CI. After
changing a dependency, regenerate it:

```powershell
.\scripts\update-constraints.ps1
```

## Branches

`main` is always releasable. Work happens on short-lived branches named
`feature/*`, `fix/*`, `docs/*` or `release/*` and is merged through pull
requests. See [../docs/team-workflow.md](../docs/team-workflow.md).
