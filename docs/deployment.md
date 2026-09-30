# Deployment

## Current state

**ParcelPulse is not deployed anywhere.** As of v0.1.0 the only environment is
the local Docker Compose stack described in
[local-development.md](local-development.md). There is no staging or
production environment, no hosting decision, no deployment pipeline and no
container registry.

This document records what exists that a deployment would build on, and what
has to be decided and built first.

## What exists

**Container images.** Each service builds an image from its own directory.
They run as non-root users and take all configuration from environment
variables.

| Image              | Built from                            | Port | Health                                       |
| ------------------ | ------------------------------------- | ---- | -------------------------------------------- |
| API                | `api/Dockerfile`                      | 8000 | `GET /health` (liveness), `GET /ready` (readiness) |
| Migration job      | same image, `alembic upgrade head`    |      | exits 0 on success                           |
| Worker             | `worker/Dockerfile`                   |      | `python -m parcelpulse_worker.healthcheck`   |
| Sweeper            | same image, `python -m parcelpulse_worker.sweeper` | | same                                 |
| Web                | `web/Dockerfile`                      | 3000 | `GET /api/health`, `GET /api/ready`          |

The carrier simulator and Mailpit are development tools and must not be
deployed.

**Configuration.** Every variable is documented in each component's
`.env.example`.

**Startup order.** Migrations run to completion before the API, worker and
sweeper start. The Compose file shows the dependencies.

## Settings that must differ from local development

| Service | Setting                     | Production value                                                        |
| ------- | --------------------------- | ----------------------------------------------------------------------- |
| API     | `ENVIRONMENT`               | `production`. The API then refuses to start with development endpoints enabled or signature checks disabled |
| API     | `ENABLE_DEV_ENDPOINTS`      | unset or `false`                                                        |
| API     | `WEBHOOK_SIGNING_SECRET`    | A generated secret from a secret store, shared with the carrier         |
| API, worker | `DATABASE_URL`, `REDIS_URL` | Managed instances with real credentials                             |
| API     | `SUPPORTED_CARRIERS`        | The real carrier codes                                                  |
| Worker  | `SMTP_*`, `EMAIL_FROM`      | A real mail provider, with `SMTP_STARTTLS=true` and credentials         |
| Worker  | `WEB_BASE_URL`              | The public URL of the dashboard                                         |
| Web     | `API_BASE_URL`              | The internal address of the API                                         |
| Web     | `ENABLE_DEV_TOOLS`          | unset                                                                   |

The Compose file's credentials and webhook secret are local-development
defaults and must not be reused.

## What has to be decided and built before a first deployment

- **Where it runs.** No hosting platform has been chosen.
- **Authentication.** The dashboard and the API's shipment endpoints have
  none. Exposing either to the internet as it is would let anyone read and
  change every shipment.
- **Network exposure.** Only the dashboard and `POST /webhooks/carrier` need to
  be reachable from outside. `/metrics` and the rest of the API should not be.
- **TLS.** Nothing terminates TLS today.
- **A real carrier integration.** The only carrier is the simulator. A real
  one needs its payload mapped to the webhook contract, or an adapter.
- **Secret management** and secret rotation. The signature check accepts more
  than one `v1` value, which allows rotating the webhook secret without
  downtime.
- **Image publishing.** CI builds the images to check that they build. It does
  not push them anywhere.
- **Database operations.** Backups, restore tests, and a rule for migrations
  that stay compatible with the running worker (see ADR-001).
- **Monitoring.** Something to scrape `/metrics`, collect the JSON logs and
  alert on failed notifications and webhook rejections.
- **Retention.** `webhook_receipts` and `notifications` grow without bound.
- **Capacity.** Process counts and connection pool sizes are defaults. See
  [load-testing.md](load-testing.md) for the first measurements.

## Release versus deployment

A release is a tag on a validated commit of this repository
([release-process.md](release-process.md)). Releasing v0.1.0 does not deploy
anything.
