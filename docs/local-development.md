# Local development

Everything runs on one machine with Docker. No carrier account, mail provider
or cloud service is needed.

## Prerequisites

- Docker Desktop (or Docker Engine with the Compose plugin)
- Git
- Only for working on a service outside Docker: Python 3.12 (API, worker,
  simulator) and Node.js 22 or newer (web)

## Layout

One checkout of this repository has everything:

```
api/   web/   worker/   infra/   workspace-tools/   docs/
```

The Compose file in `infra/` builds the services from `../api`, `../worker`
and `../web`. See [monorepo-layout.md](monorepo-layout.md).

## Start the stack

```powershell
cd infra
docker compose up --build
```

Add `-d --wait` to run it in the background and return once every service is
healthy. The first build takes a few minutes. On Windows,
`workspace-tools\start-all.ps1` does the same and prints the addresses.

| What                  | Where                                                         |
| --------------------- | ------------------------------------------------------------- |
| Dashboard             | <http://localhost:3000>                                       |
| Developer tools       | <http://localhost:3000/dev>                                   |
| API                   | <http://localhost:8000> (OpenAPI at `/docs`)                  |
| Carrier simulator     | <http://localhost:8100> (OpenAPI at `/docs`)                  |
| Mail sink (Mailpit)   | <http://localhost:8025>                                       |
| PostgreSQL            | `localhost:15432`, user, password and database `parcelpulse`  |
| Redis                 | `localhost:6379`                                              |

Startup order is handled by Compose: PostgreSQL, then the `api-migrate` job
(`alembic upgrade head`, runs once and exits), then the API, then everything
that depends on it.

### Configuration

The defaults work as they are. To change a port, a credential or the webhook
secret, copy `infra/.env.example` to `infra/.env` and edit it. `.env` is
ignored by Git.

If a port is already in use on your machine (another PostgreSQL, another
project on 3000), set the corresponding `*_HOST_PORT` in `.env`. Keep host
ports below 49152 on Windows.

The Compose project is named `parcelpulse`. To run a second copy of the stack
next to another one, set `COMPOSE_PROJECT_NAME` (and different host ports) in
`infra/.env`.

## Try it

In the browser, open <http://localhost:3000/dev>, create a simulated shipment
and press the buttons: each one makes the simulated carrier send webhooks, and
shows how ParcelPulse answered. Open the shipment to watch the timeline, and
the mail sink to see the emails.

From a terminal, in `infra/`:

```powershell
# Create a shipment at the carrier and register it in ParcelPulse
docker compose exec carrier-simulator carrier-sim create --register --notification-email me@example.com

# Use the tracking number it printed
docker compose exec carrier-simulator carrier-sim advance SCXXXXXXXXXX --count 3
docker compose exec carrier-simulator carrier-sim duplicate SCXXXXXXXXXX
docker compose exec carrier-simulator carrier-sim hold SCXXXXXXXXXX
docker compose exec carrier-simulator carrier-sim lifecycle SCXXXXXXXXXX
```

See [../infra/carrier-simulator/README.md](../infra/carrier-simulator/README.md)
for everything the simulator can do.

## Check that it works

```powershell
docker compose run --rm smoke
```

runs the end-to-end smoke test inside the Compose network. With Python 3.12 on
the host, `py -3.12 tests\smoke\smoke_test.py` does the same through the
published ports. It creates a shipment, sends events, a duplicate and a late
event, and verifies the timeline, the shipment status, that exactly one
notification and one email exist per notifiable event, webhook authentication
and the health endpoints. It exits non-zero if any check fails.

To run every check of every component, each reported separately:

```powershell
..\workspace-tools\verify-all.ps1 -Setup -Smoke
```

[testing.md](testing.md) lists what each check establishes and the commands
behind it.

## Everyday commands

From `infra/`:

```powershell
docker compose ps                        # what is running and healthy
docker compose logs -f api worker        # follow logs (JSON lines)
docker compose up -d --build api         # rebuild and restart one service
docker compose exec postgres psql -U parcelpulse -d parcelpulse
docker compose down                      # stop, keep the data
docker compose down -v                   # stop and delete database and queue
```

Following one webhook through the system: take the `X-Correlation-ID` of the
webhook response (or `correlation_id` from an API log line) and search both
services' logs for it.

```powershell
docker compose logs api worker | Select-String "<correlation id>"
```

## Working on one component

Run the stack, then replace the service you are changing with a local process.

**API**

```powershell
docker compose stop api                   # in infra/
cd ..\api
Copy-Item .env.example .env        # set WEBHOOK_SIGNING_SECRET to the value used by the stack
uvicorn parcelpulse_api.main:create_app --factory --reload --port 8000
```

The carrier simulator and the web container reach the API at `api:8000` inside
the Compose network, so they do not see a host process. Drive a host-run API
with the simulator run on the host as well, or with your own signed requests.

**Web**

```powershell
cd web
Copy-Item .env.example .env.local
npm run dev -- --port 3001
```

**Worker.** The Dramatiq worker needs `fork()`, so on Windows change the code
and rebuild the container: `docker compose up -d --build worker worker-sweeper`.

Each component's README describes its own tests. The API and the worker bring
their own throwaway PostgreSQL for tests (`docker-compose.dev.yml`), on ports
that do not collide with the stack.

## Troubleshooting

| Symptom                                           | Cause and fix                                                                 |
| ------------------------------------------------- | ----------------------------------------------------------------------------- |
| `Bind for 0.0.0.0:<port> failed: port is already allocated` | Something else uses the port. Set the matching `*_HOST_PORT` in `infra/.env` |
| `api-migrate` exits non-zero                      | Read `docker compose logs api-migrate`; usually a database left over from an incompatible schema. `docker compose down -v` starts clean |
| Webhooks answered with 401                        | The simulator and the API have different `WEBHOOK_SIGNING_SECRET` values      |
| Events answered with `UNKNOWN_SHIPMENT`           | The tracking number is not registered in ParcelPulse. Create with `--register` |
| No email arrives                                  | Check the shipment has a notification email, then `docker compose logs worker`, then the shipment's Notifications page for the status and last error |
| The test databases of `api/` or `worker/` replace containers of the main stack | `COMPOSE_PROJECT_NAME` is exported in the shell; it overrides the project name of every Compose file. Set it in `infra/.env` instead, or pass `-p` |
| Requests from the host are about 50 ms slower than expected | Docker Desktop port forwarding on Windows; see [load-testing.md](load-testing.md) |
