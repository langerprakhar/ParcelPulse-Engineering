# Changelog

All notable changes to parcelpulse-api. Versions follow semantic versioning;
while the major version is 0, a minor version may contain breaking changes.

## 0.1.0

Initial version.

### Added

- Shipment registration and lookup: `POST /shipments`, `GET /shipments`,
  `GET /shipments/{id}`, `GET /shipments/by-tracking/{tracking_number}`,
  `GET /carriers`.
- Carrier webhook ingestion at `POST /webhooks/carrier` with HMAC-SHA256
  signature verification and payload validation.
- Idempotent event storage keyed on `(provider, event_id)`; duplicates are
  acknowledged without side effects and every delivery attempt is recorded in
  `webhook_receipts`.
- Shipment state derived from all events by carrier event time, with sticky
  terminal statuses; `event_at` and `received_at` stored separately.
- Timeline at `GET /shipments/{id}/events`.
- Notification outbox written in the webhook transaction and published to
  Redis (Dramatiq) after commit; per-shipment notification preferences and
  notification history endpoints.
- `GET /health`, `GET /ready`, `GET /metrics`; structured JSON logs with
  correlation IDs; development endpoints under `/dev` when enabled.
- Alembic migrations 0001 to 0003, Docker image, CI workflow.
