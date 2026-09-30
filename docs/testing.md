# Testing

What is verified, by what, and what is not. Each kind of check below is a
separate dimension: passing one says nothing about the others.

## Verification dimensions

| # | Dimension                         | What it establishes                                                        | What it does not                                         |
| - | --------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------- |
| 1 | Lint and formatting               | Code follows the configured rules                                          | Anything about behaviour                                 |
| 2 | Type checks                       | The code is type-consistent (mypy strict; `tsc`)                           | Runtime behaviour; the contracts between components      |
| 3 | Unit tests                        | Pure logic is right: state derivation, signatures, retry schedule, formatting, form handling | That it works against a real database, broker or browser |
| 4 | Integration tests                 | A component behaves correctly against its real dependencies: PostgreSQL, Redis, an SMTP server | That components work with each other               |
| 5 | Migration checks                  | The schema builds from an empty database, matches the models, and downgrades and upgrades | That the worker's view of the schema matches          |
| 6 | Contract halves                   | Each side of a cross-component contract does what its own side promises    | That the two sides agree                                 |
| 7 | Static infrastructure checks      | The Compose file is valid: services, pinned images, healthchecks, startup order, ports | That the stack starts                            |
| 8 | Image builds                      | Each image builds and its process starts                                   | That it works with its dependencies                      |
| 9 | Full-stack smoke test             | The components work together, from an empty database, through real HTTP, the real queue and real SMTP | Every feature; browser behaviour; load        |
| 10 | Script and secret checks         | PowerShell scripts parse; no env files or token-shaped strings are tracked | That the scripts work; that no secret exists in another form |
| 11 | Load test                        | How ingestion behaved in one run, and that the data stayed correct under load | Capacity. It has no pass/fail threshold               |

## Where each dimension is checked

### api/

| Dimension | Check                                   | Command (from `api/`)                          | CI job (API CI)            |
| --------- | --------------------------------------- | ---------------------------------------------- | -------------------------- |
| 1         | ruff                                    | `ruff check .`, `ruff format --check .`        | Lint (ruff)                |
| 2         | mypy, strict                            | `mypy`                                         | Type check (mypy)          |
| 3         | State derivation, signature, payload, config, request context | `pytest tests/unit`      | Unit tests                 |
| 4         | Shipments                               | `pytest tests/integration/test_shipments_api.py` | Integration (shipments)  |
| 4         | Webhook ingestion                       | `… test_webhook_ingestion.py`                  | Integration (webhook-ingestion) |
| 4         | Duplicate and concurrent webhooks       | `… test_webhook_idempotency.py`                | Integration (webhook-idempotency) |
| 4         | Delayed and out-of-order events         | `… test_event_ordering.py`                     | Integration (event-ordering) |
| 4         | Timeline                                | `… test_timeline.py`                           | Integration (timeline)     |
| 4         | Notification outbox                     | `… test_notifications.py`                      | Integration (notifications) |
| 4         | Readiness, metrics, dev endpoints       | `… test_operations.py`                         | Integration (operations)   |
| 6         | The queue message the API publishes     | `… test_queue_publisher.py`                    | Integration (queue-publisher) |
| 5         | Migrations                              | `alembic upgrade head`, `alembic check`, `… test_migrations.py` | Migration sanity |
| 8         | Image                                   | `docker build .`                               | Docker image build         |

Integration tests need PostgreSQL and Redis:
`docker compose -f docker-compose.dev.yml up -d --wait`.

### worker/

| Dimension | Check                                     | Command (from `worker/`)            | CI job (Worker CI)                     |
| --------- | ----------------------------------------- | ----------------------------------- | -------------------------------------- |
| 1         | ruff                                      | `ruff check .`, `ruff format --check .` | Lint (ruff)                        |
| 2         | mypy, strict                              | `mypy`                              | Type check (mypy)                      |
| 3         | Config, logging, retry schedule, email content | `pytest tests/test_config.py tests/test_logging.py tests/test_retry.py tests/test_email_content.py` | Tests (unit) |
| 4         | SMTP delivery and error classification    | `pytest tests/test_smtp_sender.py`  | Tests (smtp-sender)                    |
| 4         | Exactly-once claim, retries, failure      | `pytest tests/test_delivery.py`     | Tests (delivery-idempotency-and-retry) |
| 4, 6      | The queue message the worker consumes     | `pytest tests/test_actor.py`        | Tests (queue-handling)                 |
| 4         | Sweeper                                   | `pytest tests/test_sweeper.py`      | Tests (sweeper)                        |
| 4         | Healthcheck                               | `pytest tests/test_healthcheck.py`  | Tests (healthcheck)                    |
| 8         | Image                                     | `docker build .`                    | Docker image build                     |

These tests create their tables from the worker's own mirror of the schema
(`worker/src/parcelpulse_worker/db.py`), not from the API's migrations.

### web/

| Dimension | Check                          | Command (from `web/`)            | CI job (Web CI)                   |
| --------- | ------------------------------ | -------------------------------- | --------------------------------- |
| 1         | ESLint                         | `npm run lint`                   | Lint (eslint)                     |
| 2         | TypeScript                     | `npm run typecheck`              | Type check (tsc)                  |
| 3         | API client, formatting         | `npx vitest run src/lib`         | Tests (api-client-and-formatting) |
| 3         | Server Actions                 | `npx vitest run src/actions`     | Tests (server-actions)            |
| 3         | Components                     | `npx vitest run src/components`  | Tests (components)                |
| 3         | Route handlers                 | `npx vitest run src/app`         | Tests (route-handlers)            |
| 8         | Production build               | `npm run build`                  | Production build                  |
| 8         | Image                          | `docker build .`                 | Docker image build                |

### infra/

| Dimension | Check                                | Command (from `infra/`)                         | CI job (Infra CI)                     |
| --------- | ------------------------------------ | ----------------------------------------------- | ------------------------------------- |
| 7         | Compose file                         | `docker compose config -q`, `pytest tests/test_compose.py` | Compose configuration      |
| 1, 10     | Scripts                              | `ruff check tests loadtest`; PowerShell parse   | Scripts (lint and syntax)             |
| 1, 2      | Carrier simulator lint and types     | in `carrier-simulator/`: `ruff check .`, `mypy` | Carrier simulator (lint and type check) |
| 3         | Simulator: delivery and retries      | `pytest tests/test_sender.py`                   | Carrier simulator tests (webhook-delivery-and-retries) |
| 3         | Simulator: carrier behaviours        | `pytest tests/test_simulator.py`                | Carrier simulator tests (carrier-behaviours) |
| 3         | Simulator: HTTP API and CLI          | `pytest tests/test_app.py`                      | Carrier simulator tests (http-api-and-cli) |
| 8         | Simulator image                      | `docker build carrier-simulator`                | Carrier simulator image build         |

### Whole system

| Dimension | Check                 | Command                                                       | CI                                   |
| --------- | --------------------- | ------------------------------------------------------------- | ------------------------------------ |
| 9         | Smoke test            | `docker compose up -d --build --wait`, then `docker compose run --rm smoke` (from `infra/`) | Full-stack CI |
| 10        | Secret scan           | `workspace-tools\verify-all.ps1`                              | not in CI                            |
| 11        | Load test             | `docker compose run --rm loadtest …` ([load-testing.md](load-testing.md)) | not in CI                |
| all       | Everything above, locally | `workspace-tools\verify-all.ps1 -Smoke`                   |                                      |

## What the smoke test covers

`infra/tests/smoke/smoke_test.py` drives a running stack through the carrier
simulator and reads the results back through the API, the mail sink and the
web pages. It checks, in order: health and readiness of every service;
shipment registration; three carrier events and the resulting timeline;
redelivered webhooks producing no second event; one notification sent exactly
once despite carrier retries; a late, out-of-order event joining the timeline
without moving the shipment backwards and without notifying; delivery; an
unsigned webhook being rejected; the dashboard pages rendering the shipment;
API metrics.

It is the only check of the contracts between components. If a change to the
API's responses, the queue message or the schema breaks the web application
or the worker, this is where it shows.

## Reading CI results

- **Every suite is its own job.** Look at the list of checks, not at a single
  green mark.
- **A workflow that did not run verified nothing.** Workflows have path
  filters: a commit that only touches `web/` gets no API checks. The API was
  last verified by the last commit that changed `api/`. Full-stack CI runs for
  a change to any component.
- **Changes under `docs/` and root files trigger no workflow.**
- Every workflow can be started by hand from the Actions tab
  (`workflow_dispatch`) to verify a specific commit in full.
- Test jobs attach their results to the run as JUnit XML artifacts.

## Counts

As observed on 2026-09-30, in CI and locally:

| Suite                        | Tests |
| ---------------------------- | ----- |
| API unit                     | 73    |
| API integration (9 suites, including migrations) | 109 |
| Worker                       | 82    |
| Web                          | 94    |
| Carrier simulator            | 53    |
| Compose static checks        | 24    |
| Smoke test                   | 46 checks |
| `verify-all.ps1 -Smoke`      | 47 checks |

These are a snapshot, not a requirement. The numbers in the CI logs of a given
commit are the ones that count for that commit.

## Not covered

- **The dashboard in a browser.** Pages are async Server Components and are
  not unit tested; the smoke test fetches their HTML but submits no form. There
  is no browser test suite.
- **Whether the two sides of a contract agree**, except through the smoke test.
  `web/src/lib/types.ts` and `worker/src/parcelpulse_worker/db.py` are
  maintained by hand.
- **A worker crash between sending and recording.** A test shows the row stays
  `SENDING`; nothing kills a real worker mid-send.
- **The Slack bootstrap against a real workspace.** Only the no-token and
  invalid-token paths have run.
- **The PowerShell tools in CI.** CI checks that they parse. They are run by
  hand, on Windows.
- **Performance.** There is no threshold and no regression check.
- **Security testing** beyond the webhook signature tests and the secret scan.
