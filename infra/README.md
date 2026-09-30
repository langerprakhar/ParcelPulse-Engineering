# parcelpulse-infra

Infrastructure and system-level documentation for ParcelPulse, a package
tracking and delivery notification platform.

This directory is the former `parcelpulse-infra` repository, imported with its
commit history into the ParcelPulse engineering repository. Run the commands
below from `infra/`. The Compose file builds the services from `../api`,
`../worker` and `../web`.

ParcelPulse is built from four repositories:

| Repository           | What it is                                                        |
| -------------------- | ----------------------------------------------------------------- |
| `parcelpulse-api`    | FastAPI service: shipments, carrier webhook ingestion, timeline   |
| `parcelpulse-web`    | Next.js dashboard                                                 |
| `parcelpulse-worker` | Asynchronous notification worker and sweeper                      |
| `parcelpulse-infra`  | This repository: the local stack, the carrier simulator, system tests and docs |

## Run everything

With the four repositories checked out side by side and Docker running:

```powershell
docker compose up --build
```

| What                | Where                         |
| ------------------- | ----------------------------- |
| Dashboard           | <http://localhost:3000>       |
| Developer tools     | <http://localhost:3000/dev>   |
| API (OpenAPI docs)  | <http://localhost:8000/docs>  |
| Carrier simulator   | <http://localhost:8100/docs>  |
| Mail sink           | <http://localhost:8025>       |

Then check that it works end to end:

```powershell
docker compose run --rm smoke
```

[docs/local-development.md](docs/local-development.md) has the details:
configuration, everyday commands, working on a single service,
troubleshooting.

## What is in this repository

| Path                  | Contents                                                                    |
| --------------------- | --------------------------------------------------------------------------- |
| `docker-compose.yml`  | The local stack: PostgreSQL, Redis, Mailpit, migration job, API, worker, sweeper, web, carrier simulator; smoke and load test as on-demand tools |
| `.env.example`        | Every variable the Compose file reads, with its default                     |
| `carrier-simulator/`  | A simulated carrier that sends signed tracking webhooks ([README](carrier-simulator/README.md)) |
| `tests/smoke/`        | End-to-end smoke test for a running stack                                   |
| `tests/test_compose.py` | Static checks on the Compose file                                         |
| `loadtest/`           | Load test for webhook ingestion                                             |
| `slack/`              | Slack app manifest, channel list and bootstrap script ([README](slack/README.md)) |
| `docs/`               | System documentation                                                        |

## Documentation

| Document                                                     | Answers                                              |
| ------------------------------------------------------------ | ---------------------------------------------------- |
| [docs/architecture.md](docs/architecture.md)                 | How the parts fit together and which guarantees hold |
| [docs/product-requirements.md](docs/product-requirements.md) | What the product must do, and what is out of scope   |
| [docs/local-development.md](docs/local-development.md)       | How to run and work on it locally                    |
| [docs/team-workflow.md](docs/team-workflow.md)               | Roles, branches, pull requests, definition of done   |
| [docs/release-checklist.md](docs/release-checklist.md)       | What must be true before a version is tagged         |
| [docs/deployment.md](docs/deployment.md)                     | What a deployment would need (nothing is deployed)   |
| [docs/load-testing.md](docs/load-testing.md)                 | How ingestion is load tested and what was observed   |
| [docs/adr/](docs/adr/README.md)                              | Architecture decision records                        |

Service-specific documentation lives with each service:

| Topic                               | Location                                          |
| ----------------------------------- | ------------------------------------------------- |
| API contract and webhook format     | `parcelpulse-api/docs/api-spec.md`                |
| Event ordering and state derivation | `parcelpulse-api/docs/event-processing.md`        |
| Duplicate webhooks                  | `parcelpulse-api/docs/webhook-idempotency.md`     |
| Notifications, retries, the queue   | `parcelpulse-worker/docs/notification-system.md`  |
| The dashboard                       | `parcelpulse-web/docs/frontend.md`                |

## Checks

```powershell
docker compose config -q                          # the Compose file is valid

python -m pip install -r requirements-dev.txt
python -m pytest tests/test_compose.py            # static checks on the Compose file
ruff check tests loadtest

cd carrier-simulator                              # the simulator has its own project
python -m pip install -e ".[dev]"
ruff check . ; mypy ; pytest
```

CI (`.github/workflows/ci.yml`) runs these and builds the simulator image. It
does not run the full-stack smoke test, because that needs all four
repositories; run it locally.

## Branches

`main` is always releasable. Work happens on short-lived branches named
`feature/*`, `fix/*`, `docs/*` or `release/*` and is merged through pull
requests. See [docs/team-workflow.md](docs/team-workflow.md).
