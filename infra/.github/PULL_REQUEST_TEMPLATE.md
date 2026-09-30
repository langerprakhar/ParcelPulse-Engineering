## What changes

<!-- The behaviour that is different after this PR, in a sentence or two. -->

## Why

<!-- Link the issue: Closes #123 -->

## How it was verified

<!-- For stack changes: the smoke test output. For docs: what you checked the text against. -->

## Checklist

- [ ] `docker compose config -q` and `pytest tests/test_compose.py` pass
- [ ] `docker compose run --rm smoke` passes against a stack built from this branch
- [ ] New or changed variables are in `.env.example`
- [ ] Documentation under `docs/` still describes what the system does
- [ ] No secrets, tokens or real personal data
