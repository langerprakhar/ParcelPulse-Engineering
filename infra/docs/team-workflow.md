# Team workflow

How work moves from an idea to `main`. This document defines roles and rules;
it does not name people.

## Roles

A role is a set of responsibilities. One person may hold several, and a role
may be shared.

| Role                        | Responsible for                                                                                           |
| --------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Product Manager**         | What is built and why. Owns `product-requirements.md`, milestone scope and issue priority. Decides when a requirement is met from the user's point of view |
| **Tech Lead**               | How it fits together. Owns the architecture and the ADRs, the contracts between repositories, and the decision to release. Arbitrates technical disagreements |
| **Backend Engineer**        | `parcelpulse-api` and `parcelpulse-worker`: endpoints, ingestion, state derivation, migrations, notification delivery, and their tests and docs |
| **Frontend Engineer**       | `parcelpulse-web`: screens, Server Actions, the API client and its types, accessibility, and their tests and docs |
| **QA/Reliability Engineer** | Confidence that it works and keeps working: the smoke and load tests, CI, the carrier simulator, the release checklist, incident follow-up |

### Possible AI agent roles

Roles that could later be given to AI agents. None is in use today. An agent
works through the same branches, pull requests and checks as a person, and a
person is accountable for merging its work.

| Role              | Would do                                                                                           | Would not do                                         |
| ----------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Code Agent**    | Implement an issue on a branch, with tests, and open a pull request                                | Merge its own pull request; change requirements      |
| **QA Agent**      | Write and run tests, reproduce bugs, run the smoke test against a change and report the results    | Mark an issue verified without evidence; weaken a test to make it pass |
| **Docs Agent**    | Compare documentation with the code and open pull requests where they disagree                     | Decide which of the two is right when the intent is unclear; it asks |
| **Release Agent** | Work through the release checklist, collect the evidence for each item, draft release notes        | Tag a release with an unticked item; deploy          |

## Where things happen

| Thing                        | Place                                                        |
| ---------------------------- | ------------------------------------------------------------ |
| Work items and bugs          | GitHub issues in the repository the work belongs to          |
| Code review                  | Pull requests                                                |
| Decisions                    | ADRs ([adr/](adr/README.md)); smaller ones in the pull request or issue |
| Discussion                   | Slack (see [../slack/README.md](../slack/README.md))         |
| Requirements                 | [product-requirements.md](product-requirements.md)           |

A decision made in chat is written down where the work is: on the issue, in
the pull request, or as an ADR. Chat is not the record.

## Issues

- One issue per outcome, in the repository that will change. Work that spans
  repositories gets one issue in each, linked to each other.
- Labels: one area (`backend`, `frontend`, `worker`, `infra`), one type
  (`feature`, `bug`, `documentation`, `testing`, `reliability`, `performance`,
  `product`, `release`) and one priority (`priority-high`, `priority-medium`,
  `priority-low`).
- Milestones: `v0.1 MVP`, `v0.2 Reliability`, `v0.3 Beta`.
- An issue is closed by the pull request that completes it, not by hand
  beforehand.

## Branches

`main` is the only long-lived branch and is always releasable.

| Prefix      | For                                   | Example                          |
| ----------- | ------------------------------------- | -------------------------------- |
| `feature/*` | New behaviour                         | `feature/dead-letter-processing` |
| `fix/*`     | Bug fixes                             | `fix/late-exception-notification` |
| `docs/*`    | Documentation only, including ADRs    | `docs/adr-005-authentication`    |
| `release/*` | Release preparation (version bumps, notes) | `release/v0.2.0`            |

Branches are short-lived and deleted after merging.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/) style subject:
`type: summary`, with `feat`, `fix`, `docs`, `test`, `build`, `ci`, `chore`,
`refactor` or `perf`. The body says why, and what a reader cannot see from the
diff.

## Pull requests

- Fill in the template: what changes, why, how it was verified.
- Small enough to review in one sitting.
- CI must be green. Look at the individual jobs: each test suite is its own
  job so that one that did not run is noticed.
- At least one approval from someone who holds the role for that repository.
  Changes to a cross-repository contract (REST API, queue message, database
  schema) also need the Tech Lead.
- Behaviour changes come with tests. Changes to documented behaviour come with
  the documentation change in the same pull request.
- The author merges after approval, using a squash or a merge commit
  consistently within a repository.

## Definition of done

A change is done when it is merged to `main`, its tests run in CI, the
documentation describes it, and for user-visible behaviour the Product Manager
agrees it meets the requirement. "Deployed" is a separate statement and is only
made about something that is actually running in an environment.

## Releases

Follow [release-checklist.md](release-checklist.md). The Tech Lead decides; the
QA/Reliability Engineer confirms the checklist.

## Incidents and bugs

1. Say so in `#incidents` as soon as something looks wrong for users.
2. Stabilise first, then find the cause.
3. Every incident ends with an issue labelled `bug` (and `reliability` where it
   applies) that records what happened, a test that would have caught it, and
   any documentation that turned out to be wrong.
