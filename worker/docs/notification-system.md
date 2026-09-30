# Notification system

How a tracking event becomes an email, across `parcelpulse-api` (which decides
that a notification is owed) and this repository (which delivers it).

## Flow

```
carrier webhook
      │
      ▼
parcelpulse-api ── one transaction ──▶ tracking_events row
                                       notifications row (status PENDING)
      │ after commit
      ▼
Redis queue "notifications" ──▶ worker: deliver_notification(notification_id)
                                     1. claim   PENDING/RETRYING ─▶ SENDING
                                     2. send    SMTP
                                     3. record  SENT | RETRYING | FAILED
                                           ▲
sweeper (every 15 s) ─────────────────────┘ re-publishes lost work,
                                             releases abandoned SENDING rows
```

## Which events notify

Decided by the API (`services/notifications.py` there). A newly stored event
creates a notification when:

1. its type is `OUT_FOR_DELIVERY`, `DELIVERED` or `DELIVERY_EXCEPTION`;
2. it became the shipment's current status when it was ingested (so late,
   historical events do not notify);
3. the shipment has a notification email with that type enabled.

The row is written in the same transaction as the tracking event, and a unique
constraint on `(tracking_event_id, type, channel, destination)` backs it up. A
redelivered webhook stores no new event and therefore creates no notification.

## The `notifications` table

The schema is owned and migrated by `parcelpulse-api`. `parcelpulse_worker/db.py`
mirrors the columns the worker uses.

| Column            | Written by | Meaning                                                 |
| ----------------- | ---------- | ------------------------------------------------------- |
| `status`          | both       | See the state machine below                             |
| `attempts`        | worker     | Number of claims, i.e. send attempts started            |
| `claimed_at`      | worker     | When the current or last attempt started                |
| `next_attempt_at` | worker     | Earliest time for the next attempt while `RETRYING`     |
| `sent_at`         | worker     | When the mail server accepted the message               |
| `last_error`      | worker     | Why the last attempt failed (cleared on success)        |
| `correlation_id`  | API        | Correlation ID of the webhook that caused it            |

### States

```
PENDING ──claim──▶ SENDING ──sent──────────────────▶ SENT      (terminal)
                     │  ▲
                     │  └──claim (when due)── RETRYING
                     ├──transient failure, attempts left──▶ RETRYING
                     ├──transient failure, none left──────▶ FAILED  (terminal)
                     └──permanent failure─────────────────▶ FAILED  (terminal)

SENDING ──lease expired (sweeper)──▶ RETRYING, or FAILED if no attempts are left
```

## Delivery: `delivery.deliver_notification`

1. **Claim.** One statement moves the row to `SENDING` and increments
   `attempts`, but only if it is `PENDING`, or `RETRYING` with
   `next_attempt_at` in the past:

   ```sql
   UPDATE notifications
      SET status = 'SENDING', attempts = attempts + 1, claimed_at = :now
    WHERE id = :id
      AND (status = 'PENDING' OR (status = 'RETRYING' AND next_attempt_at <= :now))
   RETURNING ...
   ```

   Of any number of concurrent callers, exactly one gets the row. Everyone
   else returns `SKIPPED`. The claim is committed before anything is sent.
2. **Send.** The message is rendered (`email_content.py`) and handed to the
   sender (`senders.py`).
3. **Record.** `SENT`; or `RETRYING` with `next_attempt_at`; or `FAILED`.

## Exactly once: what is and is not guaranteed

| Situation                                              | Emails sent |
| ------------------------------------------------------ | ----------- |
| Carrier redelivers the webhook, any number of times    | 1           |
| The queue delivers the message twice                   | 1           |
| Several workers receive the message at the same time   | 1           |
| The queue message is lost                              | 1 (the sweeper re-publishes it) |
| Send fails and is retried                              | 1 on the attempt that succeeds |
| **Worker dies after the mail server accepted the message, before recording `SENT`** | **possibly 2** |

The last row is the one window where a duplicate can occur. The row stays
`SENDING`; after `SENDING_LEASE_SECONDS` the sweeper returns it to `RETRYING`
and it is sent again, because the worker cannot know whether the first send
went out. Every message carries a stable
`Message-ID: <notification-id@notifications.parcelpulse>` so that a receiving
system can drop the repeat. Closing this window completely would need an
idempotent send API at the mail provider.

## Retries

- **Transient failures** (mail server unreachable, 4xx SMTP replies,
  authentication or sender problems, unexpected errors) are retried.
  Attempt *n+1* becomes due `NOTIFICATION_RETRY_BASE_SECONDS * 2^(n-1)` seconds
  after attempt *n* fails, capped at `NOTIFICATION_RETRY_MAX_SECONDS`: by
  default 30 s, 60 s, 120 s, 240 s.
- After `NOTIFICATION_MAX_ATTEMPTS` (default 5) the notification is `FAILED`.
- **Permanent failures** are not retried: the recipient or the message was
  refused with a 5xx SMTP reply, or the notification type or channel is not
  supported.
- When a retry is scheduled, the actor enqueues a delayed message for the same
  notification. If that message is lost, the sweeper finds the overdue row.

There is no jitter; volumes are low and a predictable schedule is easier to
reason about.

## The queue

See [adr/ADR-004-notification-queue.md](adr/ADR-004-notification-queue.md).

Contract between the two components (the API publishes without importing
worker code; `tests/test_actor.py` here and
`tests/integration/test_queue_publisher.py` there each check their side):

| Item       | Value                                                        |
| ---------- | ------------------------------------------------------------ |
| Broker     | Redis, through Dramatiq                                      |
| Queue name | `NOTIFICATION_QUEUE_NAME`, default `notifications`           |
| Actor name | `NOTIFICATION_ACTOR_NAME`, default `deliver_notification`    |
| Arguments  | `args: [notification_id]`, `kwargs: {"correlation_id": ...}` |

A message is only a wake-up call. All state is in PostgreSQL, so duplicated,
lost, delayed or reordered messages cannot duplicate or lose a notification.

The actor's own `max_retries=3` covers errors *before* the claim (for example
PostgreSQL being unreachable); those do not consume a notification attempt.
A message whose id is not a UUID is logged and dropped.

## The sweeper: `python -m parcelpulse_worker.sweeper`

Every `SWEEP_INTERVAL_SECONDS` (default 15):

1. **Releases abandoned claims.** Rows in `SENDING` for longer than
   `SENDING_LEASE_SECONDS` (default 120) go back to `RETRYING` and are
   published immediately, or to `FAILED` if their attempts are used up.
2. **Re-publishes overdue rows.** `PENDING` rows, and `RETRYING` rows past
   their `next_attempt_at`, that have not been touched for
   `SWEEP_GRACE_SECONDS` (default 30) get a new queue message. This covers an
   API that committed but could not publish, and messages lost with Redis.

Each re-publish touches `updated_at`, which limits it to once per grace period
per row and lets several sweepers run without publishing the same row twice
(`FOR UPDATE SKIP LOCKED`). While no worker is running, a stuck notification
therefore adds one small message per grace period to the queue; they are
harmless no-ops once a worker returns.

## Email content

Plain text. Subject by type:

| Type                 | Subject                              |
| -------------------- | ------------------------------------ |
| `OUT_FOR_DELIVERY`   | `Out for delivery: <tracking number>` |
| `DELIVERED`          | `Delivered: <tracking number>`       |
| `DELIVERY_EXCEPTION` | `Delivery problem: <tracking number>` |

The body gives the status, event time (UTC), location, carrier note, the
delivery estimate where it still applies, and links to the shipment and its
notification settings under `WEB_BASE_URL`. Headers
`X-ParcelPulse-Notification-Id`, `X-ParcelPulse-Notification-Type` and
`X-ParcelPulse-Shipment-Id` identify the message.

## Providers

`EMAIL_PROVIDER=smtp` sends through `SMTP_HOST`/`SMTP_PORT`, optionally with
STARTTLS and credentials. Locally this is the Mailpit sink, which accepts
everything and delivers nothing. `EMAIL_PROVIDER=log` writes the message to the
log instead.

## Operating it

- Logs are JSON, one object per line, with the correlation ID of the
  originating webhook, the notification id and the attempt number.
- `python -m parcelpulse_worker.healthcheck` exits 0 when PostgreSQL and Redis
  are reachable; the container healthcheck runs it.
- Notification status per shipment: `GET /shipments/{id}/notifications` on the
  API, or the Notifications page of the dashboard.
- Finding stuck work:

  ```sql
  SELECT status, count(*) FROM notifications GROUP BY status;
  SELECT id, attempts, last_error FROM notifications WHERE status = 'FAILED';
  ```

## Known limitations

- Email only; no SMS or push.
- `FAILED` notifications stay failed. There is no dead-letter processing or
  manual re-send yet.
- No metrics endpoint; the worker is observable through logs and the table.
- Preferences are read when the event is ingested. Changing the address
  afterwards does not redirect a notification that is already queued.
