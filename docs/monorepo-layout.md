# Monorepo layout

What lives where in this repository, and the boundaries between the parts.

```
ParcelPulse-Engineering/
├── api/               FastAPI service
├── web/               Next.js dashboard
├── worker/            Notification worker and sweeper
├── infra/             Compose stack, carrier simulator, system tests, Slack configuration
├── workspace-tools/   PowerShell utilities for the whole system
├── docs/              System documentation and system-wide ADRs
└── .github/           Workflows, issue templates, pull request template
```

## Components

A component is a top-level directory that is built, tested and versioned on
its own. There are four.

| Component | Owns                                                                                   | Toolchain                         | Image |
| --------- | -------------------------------------------------------------------------------------- | --------------------------------- | ----- |
| `api/`    | The data and the database schema (Alembic migrations); the REST API; webhook ingestion; state derivation; the notification outbox | Python 3.12, `pyproject.toml`, `constraints.txt` | `api/Dockerfile` |
| `web/`    | The dashboard. Stores nothing; every read and write goes through the API               | Node.js, `package.json`, `package-lock.json` | `web/Dockerfile` |
| `worker/` | Delivery of notifications: the queue consumer, retries, the sweeper                    | Python 3.12, `pyproject.toml`, `constraints.txt` | `worker/Dockerfile` (worker and sweeper) |
| `infra/`  | How the components run together (`docker-compose.yml`); the carrier simulator; the smoke and load tests; Slack configuration | Docker Compose; Python for the simulator and scripts | `infra/carrier-simulator/Dockerfile` |

Each component has its own `README.md`, `.env.example`, tests and
`CHANGELOG.md`. The Python packages and the npm package are still named
`parcelpulse-api`, `parcelpulse-worker`, `parcelpulse-web` and
`carrier-simulator`; those are package and service names, not locations.

## Boundaries

**No component imports another component's code.** They meet only at four
contracts, each defined in one place and mirrored by hand in another:

| Contract                   | Defined by                                  | Mirrored in                                   |
| -------------------------- | ------------------------------------------- | --------------------------------------------- |
| REST API                   | `api/` (OpenAPI; `api/docs/api-spec.md`)    | `web/src/lib/types.ts`, `web/src/lib/api.ts`  |
| Carrier webhook            | `api/docs/api-spec.md`                      | `infra/carrier-simulator/` (signing, payload) |
| Notification queue message | `worker/docs/notification-system.md`        | `api/src/parcelpulse_api/queue.py`            |
| Database schema            | `api/migrations/`                           | `worker/src/parcelpulse_worker/db.py` (the columns the worker uses) |

Being in one repository does not make these checked by a compiler. A change
to a contract must change both sides in the same pull request, and only the
full-stack smoke test verifies them together.

**Only the API writes business data.** The worker updates the delivery status
of notifications and nothing else. The web application talks only to the API,
from its server side.

**The carrier simulator is not part of the product.** It stands in for a third
party. It implements the webhook contract from the documentation, on purpose
without sharing code with the API.

## What goes where

| You are adding                                         | It goes in                                                  |
| ------------------------------------------------------ | ----------------------------------------------------------- |
| An endpoint, a model, a migration                      | `api/`                                                      |
| A screen, a form, an API client function               | `web/`                                                      |
| A notification channel, template or retry rule         | `worker/`                                                   |
| A service in the local stack, a simulator behaviour    | `infra/`                                                    |
| A check in the end-to-end smoke test                   | `infra/tests/smoke/`                                        |
| A script that operates several components              | `workspace-tools/`                                          |
| Documentation of one component's behaviour             | `<component>/docs/`                                         |
| Documentation of how components fit together, process  | `docs/`                                                     |
| A decision about one component                         | `<component>/docs/adr/`                                     |
| A decision about the system                            | `docs/adr/`                                                 |
| CI                                                     | `.github/workflows/` (the only place GitHub reads workflows from) |

ADRs are numbered across the whole repository; the index is
[adr/README.md](adr/README.md).

## How the directories map to CI

| Changed path                                  | Workflows that run                 |
| --------------------------------------------- | ---------------------------------- |
| `api/**`                                      | API CI, Full-stack CI              |
| `web/**`                                      | Web CI, Full-stack CI              |
| `worker/**`                                   | Worker CI, Full-stack CI           |
| `infra/**`                                    | Infra CI, Full-stack CI            |
| `workspace-tools/**`                          | Infra CI                           |
| `docs/**`, root files                         | none                               |
| A workflow file                               | that workflow                      |

A pull request that changes two components runs both components' workflows.

## Running things

Commands in a component's README are run from that component's directory.
The Compose stack is run from `infra/`; it builds the services from `../api`,
`../worker` and `../web`. The scripts in `workspace-tools/` find the components
relative to their own location and can be run from anywhere.

## Versions

The repository is released as a whole with one tag
([release-process.md](release-process.md)). The components keep their own
version numbers in their package metadata; at a release they are the same.
