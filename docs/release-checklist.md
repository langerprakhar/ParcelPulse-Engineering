# Release checklist

A ParcelPulse release is the same version tag on all four repositories,
created only after the whole system has been verified together. A release does
not deploy anything (see [deployment.md](deployment.md)).

Versions follow semantic versioning. While the major version is 0, a minor
version may contain breaking changes.

## 1. Prepare

- [ ] Every issue in the milestone is closed or moved to a later milestone.
- [ ] `main` of each repository contains everything intended for the release
      and nothing half-finished.
- [ ] Version numbers are updated where they are recorded:
  - `parcelpulse-api`: `pyproject.toml`, `src/parcelpulse_api/__init__.py`
  - `parcelpulse-worker`: `pyproject.toml`, `src/parcelpulse_worker/__init__.py`
  - `parcelpulse-web`: `package.json` (and `package-lock.json`)
  - `parcelpulse-infra`: `carrier-simulator/pyproject.toml`,
    `carrier-simulator/src/carrier_simulator/__init__.py`
- [ ] `constraints.txt` is regenerated if any Python dependency changed.
- [ ] Documentation describes the behaviour being released. In particular:
      `api-spec.md` for API changes, `notification-system.md` for worker
      changes, `.env.example` files for configuration changes.
- [ ] Cross-repository contracts changed in this release are changed on both
      sides: REST API (API and web types), queue message (API and worker),
      database schema (API migrations and the worker's table mirror).

## 2. Verify each repository

On the commit to be tagged, with a clean working tree (`git status`).

**parcelpulse-api**

- [ ] `ruff check .` and `ruff format --check .`
- [ ] `mypy`
- [ ] `pytest tests/unit`
- [ ] `pytest tests/integration` (needs `docker-compose.dev.yml` up)
- [ ] `alembic upgrade head` on an empty database, then `alembic check`

**parcelpulse-worker**

- [ ] `ruff check .` and `ruff format --check .`
- [ ] `mypy`
- [ ] `pytest` (needs `docker-compose.dev.yml` up)

**parcelpulse-web**

- [ ] `npm ci`
- [ ] `npm run lint`
- [ ] `npm run typecheck`
- [ ] `npm test`
- [ ] `npm run build`

**parcelpulse-infra**

- [ ] `docker compose config -q`
- [ ] `python -m pytest tests/test_compose.py`
- [ ] Carrier simulator: `ruff check .`, `mypy`, `pytest` in `carrier-simulator/`

- [ ] CI is green on the commit to be tagged, in every repository that has a
      remote. Check the individual jobs, not only the overall result: each
      suite is a separate job so that a skipped or missing one is visible.

## 3. Verify the system

- [ ] Start from nothing: `docker compose down -v`, then
      `docker compose up -d --build --wait`. All services become healthy and
      `api-migrate` exits 0. This proves the schema builds from zero.
- [ ] `docker compose run --rm smoke` passes every check. It covers the
      timeline, duplicate webhooks, a notification delivered exactly once, a
      late out-of-order event, webhook authentication and the health
      endpoints.
- [ ] Open the dashboard and walk through: search, add a shipment, simulate a
      journey from `/dev`, read the timeline, change notification preferences,
      find the emails in the mail sink.
- [ ] `docker compose logs` shows no unexpected errors during the above.
- [ ] No secrets in any repository: no real `.env` file is tracked, and a
      search for keys, tokens and passwords finds only documented
      local-development defaults.

## 4. Tag

Only when every box above is ticked. In each repository:

```powershell
git tag -a v0.1.0 -m "ParcelPulse v0.1.0"
git push origin v0.1.0
```

- [ ] The same tag exists on all four repositories.
- [ ] A GitHub release is created from each tag, with notes that list the
      changes and the known limitations.
- [ ] The milestone is closed.

## 5. Afterwards

- [ ] Anything learned while releasing is added to this checklist.
- [ ] Issues found during verification that did not block the release are
      filed.

## If a check fails

Stop. Fix it on `main` through the normal pull request process and start the
checklist again from step 2 for the repository that changed and from step 3
for the system. Do not tag a release with a known failing check.
