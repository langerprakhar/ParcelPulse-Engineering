# Release process

A ParcelPulse release is one annotated tag on `main` of this repository,
created only after the whole system has been verified together on the commit
being tagged. A release does not deploy anything (see
[deployment.md](deployment.md)).

Versions follow semantic versioning. While the major version is 0, a minor
version may contain breaking changes.

## Requirements

A commit may be tagged only when all of these hold for that commit:

1. Every pull request intended for the release is merged. Nothing
   half-finished is on `main`.
2. CI is green on `main`: the latest run of each of the five workflows that
   covers this commit's content succeeded. Look at the individual jobs. A
   workflow that did not run for a commit verified nothing; if in doubt, start
   it by hand on the commit (`workflow_dispatch`).
3. The system passes validation from a clean checkout (below).
4. The working tree is clean and `main` is pushed.
5. Known limitations are written down in the release notes.

If any check fails, stop, fix it through a pull request, and start again from
step 2 of the checklist.

## Checklist

### 1. Prepare

- [ ] Every issue in the milestone is closed or moved to a later milestone.
- [ ] Version numbers agree where they are recorded:
  - `api/pyproject.toml`, `api/src/parcelpulse_api/__init__.py`
  - `worker/pyproject.toml`, `worker/src/parcelpulse_worker/__init__.py`
  - `web/package.json` (and `package-lock.json`)
  - `infra/carrier-simulator/pyproject.toml`,
    `infra/carrier-simulator/src/carrier_simulator/__init__.py`
- [ ] `constraints.txt` is regenerated in each component whose Python
      dependencies changed.
- [ ] Each changed component's `CHANGELOG.md` has an entry.
- [ ] Release notes exist at `docs/releases/<version>.md`: what the version
      does, as observed, and its known limitations.
- [ ] Documentation describes the behaviour being released.
- [ ] Contracts changed in this release are changed on both sides: REST API
      (`api/` and `web/src/lib/types.ts`), queue message (`api/` and
      `worker/`), database schema (`api/migrations/` and
      `worker/src/parcelpulse_worker/db.py`).

### 2. Verify in CI

- [ ] API CI, Web CI, Worker CI, Infra CI and Full-stack CI have each succeeded
      on `main` for the content being released.

### 3. Verify from a clean checkout

In a fresh clone of `main` at the commit to be tagged:

- [ ] `workspace-tools\verify-all.ps1 -Setup` passes every check. It runs, for
      each component, lint, formatting, type checks and every test suite as a
      separate check, plus Compose validation, workflow and script syntax and a
      secret scan. Nothing may be `BLOCKED` or `SKIPPED`.
- [ ] Start from nothing: `workspace-tools\start-all.ps1 -Fresh`. All services
      become healthy and `api-migrate` exits 0 having applied every migration
      to an empty database.
- [ ] `workspace-tools\smoke-test.ps1` passes every check. It covers the
      timeline, duplicate webhooks, a notification delivered exactly once, a
      late out-of-order event, webhook authentication and the health
      endpoints.
- [ ] The dashboard works against the real API: search, add a shipment,
      simulate a journey from `/dev`, read the timeline, change notification
      preferences, find the emails in the mail sink.
- [ ] `docker compose logs` shows no unexpected errors during the above.
- [ ] Record the actual numbers of tests and checks that ran. Do not copy them
      from a previous release.

Without PowerShell, the same checks are the commands listed in
[testing.md](testing.md).

### 4. Tag

Only when every box above is ticked:

```powershell
git tag -a v0.1.0 -m "ParcelPulse v0.1.0 engineering baseline"
git push origin v0.1.0
```

- [ ] The tag is annotated and points at the validated commit.
- [ ] A GitHub release is created from the tag, using the release notes.
- [ ] The milestone is closed.

### 5. Afterwards

- [ ] Anything learned while releasing is added to this document.
- [ ] Issues found during verification that did not block the release are
      filed.

## What a release is not

- It is not a deployment. There is no deployed environment.
- It is not a statement that the backlog is empty. Open issues and known
  limitations ship with every release and are listed in its notes.
