# parcelpulse-infra

How the ParcelPulse components run together: the Docker Compose stack, the
carrier simulator, the end-to-end smoke test, the load test and the Slack
configuration.

This directory is the former `parcelpulse-infra` repository, imported with its
commit history into the ParcelPulse engineering repository. Run the commands
below from `infra/`. System documentation that used to live here is now in
[`../docs/`](../docs/).

## Run everything

With Docker running:

```powershell
docker compose up --build
```

The Compose file builds the services from `../api`, `../worker` and `../web`.

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

[../docs/local-development.md](../docs/local-development.md) has the details:
configuration, everyday commands, working on a single component,
troubleshooting.

## What is in this directory

| Path                    | Contents                                                                    |
| ----------------------- | --------------------------------------------------------------------------- |
| `docker-compose.yml`    | The local stack: PostgreSQL, Redis, Mailpit, migration job, API, worker, sweeper, web, carrier simulator; smoke and load test as on-demand tools |
| `.env.example`          | Every variable the Compose file reads, with its default                     |
| `carrier-simulator/`    | A simulated carrier that sends signed tracking webhooks ([README](carrier-simulator/README.md)) |
| `tests/smoke/`          | End-to-end smoke test for a running stack                                   |
| `tests/test_compose.py` | Static checks on the Compose file                                           |
| `loadtest/`             | Load test for webhook ingestion ([../docs/load-testing.md](../docs/load-testing.md)) |
| `slack/`                | Slack app manifest, channel list and bootstrap script ([README](slack/README.md)) |

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

In CI these are the Infra CI workflow. The smoke test runs in the Full-stack CI
workflow, which builds and starts the whole stack on the runner. See
[../docs/testing.md](../docs/testing.md).
