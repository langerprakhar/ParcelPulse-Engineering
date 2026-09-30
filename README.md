# ParcelPulse Engineering

The canonical repository for ParcelPulse, a package tracking and delivery
notification platform. Users register a tracking number, carriers report events
by webhook, ParcelPulse keeps each shipment's timeline and current status, and
notifies the user at the moments that matter.

## Layout

| Directory          | What it is                                                              |
| ------------------ | ----------------------------------------------------------------------- |
| `api/`             | FastAPI service: shipments, carrier webhook ingestion, timeline, notification outbox |
| `web/`             | Next.js dashboard                                                       |
| `worker/`          | Notification worker and sweeper                                         |
| `infra/`           | Docker Compose stack, carrier simulator, smoke and load tests, Slack configuration |
| `workspace-tools/` | PowerShell utilities: start, stop, verify and smoke-test the whole system |
| `docs/`            | System documentation                                                    |

Each component keeps its own README, dependencies, tests, Dockerfile and
changelog. [docs/monorepo-layout.md](docs/monorepo-layout.md) describes the
boundaries between them.

## Run it

With Docker running:

```powershell
cd infra
docker compose up --build
```

| What               | Where                        |
| ------------------ | ---------------------------- |
| Dashboard          | <http://localhost:3000>      |
| Developer tools    | <http://localhost:3000/dev>  |
| API (OpenAPI docs) | <http://localhost:8000/docs> |
| Carrier simulator  | <http://localhost:8100/docs> |
| Mail sink          | <http://localhost:8025>      |

Check that it works end to end:

```powershell
docker compose run --rm smoke
```

[docs/local-development.md](docs/local-development.md) has the details.

## Documentation

| Document                                                     | Answers                                              |
| ------------------------------------------------------------ | ---------------------------------------------------- |
| [docs/architecture.md](docs/architecture.md)                 | How the parts fit together and which guarantees hold |
| [docs/monorepo-layout.md](docs/monorepo-layout.md)           | What belongs where, and what may depend on what      |
| [docs/product-requirements.md](docs/product-requirements.md) | What the product must do, and what is out of scope   |
| [docs/local-development.md](docs/local-development.md)       | How to run and work on it locally                    |
| [docs/testing.md](docs/testing.md)                           | What is verified, how, and what is not               |
| [docs/team-workflow.md](docs/team-workflow.md)               | Roles, issues, branches, pull requests               |
| [docs/release-process.md](docs/release-process.md)           | What must be true before a version is tagged         |
| [docs/deployment.md](docs/deployment.md)                     | What a deployment would need (nothing is deployed)   |
| [docs/load-testing.md](docs/load-testing.md)                 | How ingestion is load tested and what was observed   |
| [docs/engineering-history.md](docs/engineering-history.md)   | Where this repository's contents and history came from |
| [docs/adr/](docs/adr/README.md)                              | Architecture decision records                        |

Component documentation:

| Topic                               | Location                                                               |
| ----------------------------------- | ---------------------------------------------------------------------- |
| API contract and webhook format     | [api/docs/api-spec.md](api/docs/api-spec.md)                           |
| Event ordering and state derivation | [api/docs/event-processing.md](api/docs/event-processing.md)           |
| Duplicate webhooks                  | [api/docs/webhook-idempotency.md](api/docs/webhook-idempotency.md)     |
| Notifications, retries, the queue   | [worker/docs/notification-system.md](worker/docs/notification-system.md) |
| The dashboard                       | [web/docs/frontend.md](web/docs/frontend.md)                           |
| The carrier simulator               | [infra/carrier-simulator/README.md](infra/carrier-simulator/README.md) |

## Continuous integration

Five workflows in `.github/workflows/`. Each of the first four runs when its
component changes; the last runs when any component changes.

| Workflow        | Checks                                                                       |
| --------------- | ---------------------------------------------------------------------------- |
| API CI          | ruff, mypy, unit tests, each integration suite, migrations, image build      |
| Web CI          | eslint, typecheck, each test area, production build, image build             |
| Worker CI       | ruff, mypy, each test suite, image build                                     |
| Infra CI        | Compose configuration, script checks, carrier simulator lint, tests and image |
| Full-stack CI   | Build the stack, start it from an empty database, end-to-end smoke test      |

A workflow that did not run for a commit says nothing about that commit. See
[docs/testing.md](docs/testing.md).

## Where this came from

ParcelPulse was first built as four independent repositories. They were
imported here with their commit histories. The commits that built each
component are part of this repository's history, alongside the pull requests
that integrated them. [docs/engineering-history.md](docs/engineering-history.md)
has the source commits and explains how to read the history.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
