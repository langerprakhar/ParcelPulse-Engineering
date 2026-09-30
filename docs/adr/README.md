# Architecture decision records

An ADR records one decision: the context, what was decided, the alternatives
that were rejected and the consequences accepted. ADRs are numbered across the
whole repository. A decision about one component lives with that component; a
decision about the system lives here.

| ADR     | Decision                     | Location                                                                                                  | Status   |
| ------- | ---------------------------- | --------------------------------------------------------------------------------------------------------- | -------- |
| ADR-001 | Service architecture         | [ADR-001-service-architecture.md](ADR-001-service-architecture.md)                                        | Accepted; its repository layout is superseded by ADR-005 |
| ADR-002 | Webhook idempotency strategy | [api/docs/adr/ADR-002-webhook-idempotency.md](../../api/docs/adr/ADR-002-webhook-idempotency.md)          | Accepted |
| ADR-003 | Event ordering semantics     | [api/docs/adr/ADR-003-event-ordering.md](../../api/docs/adr/ADR-003-event-ordering.md)                    | Accepted |
| ADR-004 | Notification queue choice    | [worker/docs/adr/ADR-004-notification-queue.md](../../worker/docs/adr/ADR-004-notification-queue.md)      | Accepted |
| ADR-005 | Single engineering repository | [ADR-005-single-repository.md](ADR-005-single-repository.md)                                             | Accepted |

## Writing a new one

1. Take the next number and add a row here.
2. Use the headings of the existing ADRs: Status, Date, Context, Decision,
   Alternatives considered, Consequences.
3. Open it as a pull request on a `docs/*` branch. It is "Proposed" until
   merged.
4. An accepted ADR is not edited to change the decision. Write a new ADR that
   supersedes it and update the status of the old one.
