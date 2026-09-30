# ADR-001: Service architecture

- Status: Accepted. The repository layout decided here (one repository per
  service) is superseded by [ADR-005](ADR-005-single-repository.md). The
  service architecture stands.
- Date: 2026-09-30

## Context

ParcelPulse has three kinds of work with different shapes:

- serving a dashboard to people,
- accepting carrier webhooks, which arrive in bursts, are retried, and must be
  answered quickly and correctly,
- sending notifications, which is slow, can fail, and must not hold up a
  webhook response.

The team is small. The system should be understandable by one person and run
on a laptop with one command.

## Decision

Three deployable services and two backing stores, each service in its own
repository:

| Service | Repository           | Role                                                    |
| ------- | -------------------- | ------------------------------------------------------- |
| Web     | `parcelpulse-web`    | Next.js dashboard. Calls the API from the server side   |
| API     | `parcelpulse-api`    | The only writer of business data; owns the schema       |
| Worker  | `parcelpulse-worker` | Asynchronous notification delivery (worker and sweeper) |

- **PostgreSQL** is the single system of record.
- **Redis** is a message broker only.
- The **API and worker share the database**. The API owns and migrates the
  schema; the worker reads shipments and events and updates notification
  status.
- The **web application talks only to the API**, from its server side. The
  browser never calls the API directly.
- A fourth repository, `parcelpulse-infra`, holds the Compose stack, the
  carrier simulator and system documentation.
- Local orchestration is **Docker Compose**.

## Alternatives considered

**One service (a monolith) with a background thread for notifications.**
Least to operate, but a notification backlog or a slow mail server would share
a process with webhook handling, and the worker could not be scaled or
restarted independently.

**One repository for everything.** Simpler cross-cutting changes and one CI
run. We chose separate repositories because the three services are built with
different toolchains and can be versioned and released separately. The cost
is that contracts between them (REST, queue message, schema) are not checked
by a compiler and need tests and documentation.

**Worker without database access**, calling internal API endpoints to claim
and complete notifications. Cleaner ownership of the schema, but it adds an
internal API surface and a network hop to every state change, and the worker's
atomic claim is simplest as a single SQL statement. Revisit if a second
consumer of the notification data appears.

**Finer-grained services** (separate ingestion service, separate read API).
No current need; every split adds a contract to maintain.

**Kubernetes, Kafka, a search engine.** Not justified by anything the product
does today.

## Consequences

- Each service can be built, tested and released on its own, with its own CI.
- Three cross-repository contracts must be kept in step by hand: the REST API
  (API and web), the queue message (API and worker) and the database schema
  (API and worker). A change to one is two pull requests. The full-stack smoke
  test is the safety net, and it currently runs locally, not in CI.
- The API is a single point of failure for both the dashboard and ingestion.
- Shared-database coupling means a schema change must stay compatible with the
  deployed worker, or both must be released together.
- Local development needs all repositories checked out side by side.
