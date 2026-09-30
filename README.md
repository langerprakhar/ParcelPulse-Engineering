# ParcelPulse Engineering

The canonical repository for ParcelPulse, a package tracking and delivery
notification platform. Users register a tracking number, carriers report events
by webhook, ParcelPulse keeps each shipment's timeline and current status, and
notifies the user at the moments that matter.

## Status

This repository is being assembled. ParcelPulse was first built as four
independent repositories. Each one is imported here, with its commit history,
through its own pull request:

| Directory          | Component                                      | Imported from        |
| ------------------ | ---------------------------------------------- | -------------------- |
| `api/`             | FastAPI service: shipments, webhook ingestion  | `parcelpulse-api`    |
| `web/`             | Next.js dashboard                              | `parcelpulse-web`    |
| `worker/`          | Notification worker and sweeper                | `parcelpulse-worker` |
| `infra/`           | Compose stack, carrier simulator, system tests | `parcelpulse-infra`  |
| `workspace-tools/` | PowerShell utilities for the whole workspace   | unversioned tooling  |

A directory exists once its import has been merged.
[docs/engineering-history.md](docs/engineering-history.md) records where each
component came from and at which commit.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
