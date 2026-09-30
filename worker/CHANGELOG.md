# Changelog

All notable changes to parcelpulse-worker. Versions follow semantic versioning;
while the major version is 0, a minor version may contain breaking changes.

## 0.1.0

Initial version.

### Added

- Dramatiq actor `deliver_notification` on the `notifications` queue.
- Notification delivery with an atomic claim in PostgreSQL, so duplicated,
  concurrent or repeated queue messages send one email.
- Email rendering for out for delivery, delivered and delivery exception, with
  a stable Message-ID per notification.
- SMTP sender with transient/permanent error classification; log sender.
- Retry policy: exponential backoff, maximum attempts, permanent failures not
  retried.
- Sweeper process that re-publishes lost messages and releases notifications
  abandoned mid-send.
- Dependency healthcheck command, Docker image, CI workflow.
