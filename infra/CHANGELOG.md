# Changelog

All notable changes to parcelpulse-infra. Versions follow semantic versioning;
while the major version is 0, a minor version may contain breaking changes.

Release notes for ParcelPulse as a whole are in `docs/releases/` at the
repository root.

## 0.1.0

Initial version.

### Added

- Docker Compose stack: PostgreSQL, Redis, Mailpit, migration job, API, worker,
  sweeper, web dashboard and carrier simulator, with health-based startup
  order.
- Carrier simulator with an HTTP API and the `carrier-sim` command line.
- End-to-end smoke test and static Compose checks.
- Webhook ingestion load test.
- Slack app manifest and channel bootstrap script.
- System documentation: architecture, product requirements, local development,
  team workflow, release checklist, deployment, load testing, ADR-001.
- CI workflow.
