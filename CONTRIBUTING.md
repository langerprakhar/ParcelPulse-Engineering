# Contributing

## Branches

`main` is the only long-lived branch and should always be releasable. Work
happens on short-lived branches and reaches `main` through a pull request.

| Prefix          | For                                                         |
| --------------- | ----------------------------------------------------------- |
| `feature/*`     | New behaviour                                               |
| `fix/*`         | Bug fixes                                                   |
| `docs/*`        | Documentation only, including ADRs                          |
| `release/*`     | Release preparation                                         |
| `integration/*` | Bringing the previously independent components into this repository |

## Commits

[Conventional Commits](https://www.conventionalcommits.org/) style subject,
optionally scoped to a component: `feat(api): ...`, `fix(worker): ...`,
`docs: ...`. The body says why, and what a reader cannot see from the diff.

## Pull requests

- Link the issue the pull request addresses.
- Say what changes, why, and how it was verified. Report the checks that were
  actually run and their actual results.
- Behaviour changes come with tests. Changes to documented behaviour come with
  the documentation change in the same pull request.
- Pull requests are merged with a merge commit. Squashing is not used for
  pull requests that carry imported history, because it would discard the
  original commits.
- Do not force-push a branch after it has been pushed for review or CI. Fix
  problems with follow-up commits.

## History

Commits imported from the original component repositories are kept exactly as
they were written: same content, authors and dates. They are not rewritten,
reordered or squashed.
