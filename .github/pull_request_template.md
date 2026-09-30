## What changes

<!-- The behaviour that is different after this PR, in a sentence or two. -->

## Why

<!-- The issue this addresses: #123. After merging, check that the issue actually closed. -->

## How it was verified

<!-- The checks that were actually run and their actual results. Say what was not run. -->

## Checklist

- [ ] Tests cover the change, including the failure cases
- [ ] Documentation (`docs/`, the component's `docs/` and README) still describes the behaviour
- [ ] No secrets, tokens or real personal data in code, tests or logs

Tick the ones that apply to the components this PR touches:

**api/**
- [ ] A schema change has an Alembic revision and `alembic check` passes
- [ ] A change to a response shape is matched in `web/src/lib/types.ts`
- [ ] A change to the notification message or to the `notifications` table is matched in `worker/`

**web/**
- [ ] The page works with the API unavailable (it explains, it does not crash)
- [ ] Usable by keyboard and readable in both light and dark schemes

**worker/**
- [ ] The queue contract (queue name, actor name, arguments) is unchanged, or changed in `api/` too
- [ ] `worker/src/parcelpulse_worker/db.py` still matches the columns the API's migrations create

**infra/**
- [ ] `docker compose config -q` and `pytest tests/test_compose.py` pass
- [ ] New or changed variables are in `infra/.env.example`
- [ ] The smoke test passes against a stack built from this branch
