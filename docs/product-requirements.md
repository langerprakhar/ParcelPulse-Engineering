# Product requirements

## What ParcelPulse is

A package tracking and delivery notification service. A person adds the
tracking number of a parcel they are waiting for. ParcelPulse receives the
carrier's tracking events, shows where the parcel is and what has happened to
it, and sends an email at the moments the person cares about.

## Who it is for

Someone expecting a parcel who wants one place to see its progress and does
not want to keep checking. In v0.1 there are no accounts: a shipment is
reached by its tracking number or its link.

## MVP requirements (v0.1)

| #   | Requirement                                                              | Status in v0.1.0 |
| --- | ------------------------------------------------------------------------ | ---------------- |
| R1  | A shipment can be registered by tracking number and carrier              | Done             |
| R2  | Carrier webhook events update the shipment's timeline and current status | Done             |
| R3  | Duplicate webhook events are safe: no duplicate event, status change or notification | Done |
| R4  | Out-of-order and delayed events are kept in the timeline without corrupting the current status | Done |
| R5  | A user can view a shipment's timeline, with locations and event times    | Done             |
| R6  | A user can receive notifications for meaningful events                   | Done (email)     |
| R7  | The whole system runs locally with one command                           | Done             |
| R8  | CI validates every component                                             | Done: five workflows at the repository root, including the full-stack smoke test |
| R9  | Every key behaviour has automated tests                                  | Done             |
| R10 | Code, documentation, tests and infrastructure can be inspected independently per component | Done |

### R1 Registering a shipment

- A tracking number is 6 to 40 letters and digits. Spaces, dashes and case are
  ignored.
- The carrier must be one ParcelPulse supports.
- A given tracking number can be registered once per carrier. Registering it
  again leads to the existing shipment.
- An email address for notifications may be given at registration.

### R2 to R4 Tracking events

- The current status is one of: awaiting carrier, label created, in transit,
  at distribution centre, out for delivery, delivered, delivery exception,
  returned to sender.
- **Ordering decision.** The current status is derived from what the events
  mean and from the time the carrier says they happened, not from the order in
  which ParcelPulse received them. The time of receipt is recorded separately.
- A parcel that has been delivered or returned stays that way.
- An event the carrier sends more than once is recorded once.
- Events for a tracking number nobody registered are ignored.

### R5 Viewing

- Search by tracking number.
- A list of all shipments, filterable by status.
- A shipment page with status, estimated delivery, last update and the
  timeline. Each entry shows what happened, where, when it happened and when
  ParcelPulse learned of it. Events that were reported late are marked.

### R6 Notifications

- Email, for: out for delivery, delivered, delivery exception.
- Per shipment, the user chooses the address and which of the three they want.
- One notification per event, even if the carrier repeats the event.
- Old news does not notify: an event that arrives after the shipment has moved
  on is recorded but not announced.

### Estimated delivery

- **ETA decision.** ParcelPulse shows the carrier's estimate when the carrier
  provides one, and nothing otherwise. It does not calculate an estimate of its
  own. A model-based estimate is future work and out of scope for the MVP.

## Out of scope for v0.1

- User accounts, sign-in and any access control
- Real carrier integrations (a carrier simulator stands in)
- SMS, push or in-app notifications
- ParcelPulse's own delivery-time predictions
- Discovering shipments automatically (from email, from retailers)
- Multiple languages
- A deployed environment

## Quality requirements

- A webhook is never lost silently: it is stored, reported as a duplicate, or
  rejected with a reason, and every accepted delivery is auditable.
- A failed notification is retried, and if it cannot be delivered its failure
  is visible.
- No secrets in source control.
- Development and debugging endpoints are unavailable in a production
  configuration.

There are no numeric performance or availability targets yet.

## Roadmap

| Milestone        | Theme                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------- |
| v0.1.0 engineering baseline | The requirements above, running locally, integrated into one repository with CI |
| v0.2 Reliability | Dead-letter handling, retention, the notification crash window, browser tests, performance investigation |
| v0.3 Beta        | Accounts and access control, a first real carrier, a deployed environment, a pilot      |

The backlog is tracked as GitHub issues against these milestones.
