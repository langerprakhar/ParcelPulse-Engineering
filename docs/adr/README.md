# Architecture decision records

An ADR records one decision: the context, what was decided, the alternatives
that were rejected and the consequences accepted. ADRs are numbered across the
whole system and live in the repository the decision mostly concerns.

| ADR     | Decision                          | Location                                                      | Status   |
| ------- | --------------------------------- | ------------------------------------------------------------- | -------- |
| ADR-001 | Service architecture              | [ADR-001-service-architecture.md](ADR-001-service-architecture.md) (this repository) | Accepted |
| ADR-002 | Webhook idempotency strategy      | `parcelpulse-api/docs/adr/ADR-002-webhook-idempotency.md`     | Accepted |
| ADR-003 | Event ordering semantics          | `parcelpulse-api/docs/adr/ADR-003-event-ordering.md`          | Accepted |
| ADR-004 | Notification queue choice         | `parcelpulse-worker/docs/adr/ADR-004-notification-queue.md`   | Accepted |

## Writing a new one

1. Take the next number, whichever repository it goes in, and add a row here.
2. Use the headings of the existing ADRs: Status, Date, Context, Decision,
   Alternatives considered, Consequences.
3. Open it as a pull request on a `docs/*` branch. It is "Proposed" until
   merged.
4. An accepted ADR is not edited to change the decision. Write a new ADR that
   supersedes it and update the status of the old one.
