# ADR-005: Single engineering repository

- Status: Accepted
- Date: 2026-09-30
- Supersedes: the repository layout in ADR-001. The service architecture in
  ADR-001 is unchanged.

## Context

ADR-001 put each service in its own repository: `parcelpulse-api`,
`parcelpulse-web`, `parcelpulse-worker`, and `parcelpulse-infra` for the
Compose stack and system documentation. The system was built that way.

By the time the first version was complete, before any of the four
repositories had been pushed to a remote, the layout had shown these costs:

- **The contracts between services could not be checked where changes were
  made.** The REST API, the queue message and the database schema are each
  defined in one repository and mirrored by hand in another. Only the
  full-stack smoke test verifies them together, and it needs all four
  checkouts. ADR-001 recorded that it therefore ran locally and not in CI.
- **Things that belong to the whole system had no home.** System
  documentation was put in the infrastructure repository for want of a better
  place. The scripts that start, verify and smoke-test everything were in an
  unversioned directory next to the repositories.
- **A release was four tags that had to agree**, and the v0.1.0 release that
  was prepared that way was never tagged.
- **Setting up hosting meant doing everything four times**: four
  repositories, four sets of labels and milestones, four CI configurations,
  and a backlog split by repository.

The project owner decided to make one repository the canonical home of
ParcelPulse before publishing anything.

## Decision

ParcelPulse lives in one repository, `ParcelPulse-Engineering`, with one
top-level directory per component: `api/`, `web/`, `worker/`, `infra/`, plus
`workspace-tools/` and `docs/`.

- The four existing repositories are imported with their commit histories, not
  as snapshots. Their commits are kept unchanged.
- The components stay separate inside the repository: no shared code, their
  own dependencies, tests, images and changelogs. The service architecture of
  ADR-001 (three services, PostgreSQL as the system of record, Redis as a
  broker, the web application talking only to the API) does not change.
- CI is defined once, at the root, with one workflow per component and one for
  the full stack.
- A release is one tag.
- The original repositories are kept as they were, as provenance, and are not
  developed further.

See [../monorepo-layout.md](../monorepo-layout.md) and
[../engineering-history.md](../engineering-history.md).

## Alternatives considered

**Keep four repositories and push them as they were.** The tooling for that
existed (a bootstrap script for four GitHub repositories) and was abandoned
before it was run. It would have kept the costs above; in particular the
full-stack smoke test would have needed access to the other repositories from
each repository's CI.

**One repository, started from a snapshot of the current files.** Simplest to
create, but it would have discarded the commits that show how each component
was built.

**One repository with the histories rewritten** so that every old commit
appears under its new directory (for example with `git filter-repo`). That
gives a cleaner `git log` for a path, but it changes every commit's SHA and
content. The imported history would no longer be the history that was
actually written.

**A meta-repository with Git submodules.** Keeps four repositories and adds a
fifth; a change across two components would still be several commits in
several places.

## Consequences

- A change that spans components (for example an API response and the web
  types that mirror it) is one pull request and is verified together by
  Full-stack CI. This was the main thing the old layout could not do.
- The contracts are still mirrored by hand. One repository does not make a
  compiler check them.
- CI needs path filters so that every change does not run everything. A
  workflow that does not run for a commit says nothing about that commit,
  which readers of CI results have to keep in mind.
- Imported commits have their original paths. `git log -- api/<file>` stops at
  the import; seeing a file's earlier history needs `--follow -m`,
  `--full-history` with the old path, or `git blame`.
- Components can no longer be versioned or released independently. Nothing
  needed that yet.
- Documentation written for four repositories had to be revised, and the old
  wording remains in the imported history.
- Access control, if it is ever wanted per component, would have to be done
  with code owners rather than repository permissions.
