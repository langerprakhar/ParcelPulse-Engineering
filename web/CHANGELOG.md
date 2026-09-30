# Changelog

All notable changes to parcelpulse-web. Versions follow semantic versioning;
while the major version is 0, a minor version may contain breaking changes.

## 0.1.0

Initial version.

### Added

- Home page with tracking search, shipment registration and recent shipments.
- Shipment list with status filter and pagination.
- Shipment page with status, estimate, last update and a timeline ordered by
  carrier event time, showing event and receipt times and marking late events.
- Notification preferences and notification history per shipment.
- Developer tools at `/dev` for the carrier simulator, available only with
  `ENABLE_DEV_TOOLS=true`.
- `/api/health` and `/api/ready`.
- Docker image (Next.js standalone) and CI workflow.
