# parcelpulse-worker

Asynchronous notification worker for ParcelPulse, a package tracking and
delivery notification platform.

This directory is the former `parcelpulse-worker` repository, imported with its
commit history into the ParcelPulse engineering repository. Run the commands
below from `worker/`.

`parcelpulse-api` decides which notifications are owed and writes them to the
`notifications` table. This service delivers them by email, exactly once per
notification under normal operation, with retries and a recovery sweeper.

```
parcelpulse-api ──(row in notifications + Redis message)──▶ worker ──SMTP──▶ mail server
                                                              ▲
                                        sweeper ──────────────┘  (re-publishes lost work)
```

Two processes run from the same image:

| Process | Command                                                  | Purpose                                                         |
| ------- | -------------------------------------------------------- | --------------------------------------------------------------- |
| worker  | `dramatiq parcelpulse_worker.actors`                      | Consumes the queue and sends notifications                      |
| sweeper | `python -m parcelpulse_worker.sweeper`                    | Re-publishes lost messages and releases abandoned sends         |

See [docs/notification-system.md](docs/notification-system.md) for the design
and [docs/adr/ADR-004-notification-queue.md](docs/adr/ADR-004-notification-queue.md)
for why Dramatiq on Redis was chosen.

## Requirements

- Python 3.12
- PostgreSQL 17 with the schema from `parcelpulse-api` (a disposable database is provided for tests)
- Redis 7
- An SMTP server (locally: the Mailpit sink in the `infra/` stack)

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

All configuration is read from environment variables; `.env.example` lists
every one with its default.

## Run

The usual way to run the worker is the full stack in `infra/`
(`docker compose up --build`). To run it directly against that stack's
PostgreSQL, Redis and Mailpit:

```powershell
python -m parcelpulse_worker.sweeper        # in one terminal
dramatiq parcelpulse_worker.actors          # in another (Linux, macOS or WSL)
```

The Dramatiq command-line worker forks processes and is meant for Linux
containers; on Windows run the worker through Docker. The test suite runs
natively on Windows because it drives the actor through Dramatiq's in-memory
broker.

## Tests

Most tests need PostgreSQL. They create their tables from the worker's own
mirror of the schema (`parcelpulse_worker/db.py`) and empty them before each
test.

```powershell
docker compose -f docker-compose.dev.yml up -d --wait   # PostgreSQL on localhost:25433
pytest
docker compose -f docker-compose.dev.yml down
```

| File                          | What it covers                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------- |
| `tests/test_delivery.py`      | Atomic claim, exactly-once under duplicate and concurrent calls, retry, failure |
| `tests/test_actor.py`         | Queue handling through a real Dramatiq worker on the in-memory broker           |
| `tests/test_sweeper.py`       | Recovery of lost messages and abandoned sends                                   |
| `tests/test_smtp_sender.py`   | SMTP delivery and error classification against an in-process SMTP server        |
| `tests/test_email_content.py` | Message subjects, bodies and headers                                            |

Set `TEST_DATABASE_URL` to use a different database. Its name must end in
`_test`, because the test run drops and recreates the tables.

## Checks

```powershell
ruff check .
ruff format --check .
mypy
```

## Dependencies

Direct dependencies are pinned in `pyproject.toml`. `constraints.txt` pins the
full resolved set for Linux and is used by the Docker image and CI. After
changing a dependency, regenerate it:

```powershell
.\scripts\update-constraints.ps1
```

## Branches

`main` is always releasable. Work happens on short-lived branches named
`feature/*`, `fix/*`, `docs/*` or `release/*` and is merged through pull requests.
