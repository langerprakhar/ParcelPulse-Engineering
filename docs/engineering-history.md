# Engineering history

Where the contents and the commit history of this repository came from.

## Two phases

**1. Four independent repositories.** ParcelPulse was first developed as four
local Git repositories, one per component, on 2026-09-30. None of them was
ever pushed to a remote, tagged, or run through CI.

| Source repository    | Component                                      | Commits | First commit           | Last commit            |
| -------------------- | ---------------------------------------------- | ------- | ---------------------- | ---------------------- |
| `parcelpulse-api`    | FastAPI service                                | 10      | `921cd92`, 07:59 -04:00 | `7f5be87`, 09:41 -04:00 |
| `parcelpulse-web`    | Next.js dashboard                              | 11      | `d7cf999`, 08:59 -04:00 | `8dff665`, 09:41 -04:00 |
| `parcelpulse-worker` | Notification worker and sweeper                | 8       | `d70a0c6`, 08:29 -04:00 | `8d17a8e`, 09:41 -04:00 |
| `parcelpulse-infra`  | Compose stack, carrier simulator, system docs  | 11      | `c248ae8`, 08:44 -04:00 | `e7f30c7`, 09:50 -04:00 |

**2. One repository.** `ParcelPulse-Engineering` was created afterwards, on the
same day, to be the single canonical repository
([ADR-005](adr/ADR-005-single-repository.md)). The four components were
imported one at a time, each through its own pull request, with their commits
preserved. Work continues here. The four source repositories are kept,
unchanged, as provenance; they are not developed further.

## The two kinds of history

They sit side by side in `git log` and must not be confused.

- **Imported commits** are the original development history of a component,
  written before this repository existed. They were not rewritten: they have
  the same SHAs, authors, dates and messages as in the source repositories.
  In them, files are at the paths they had in the source repository
  (`src/...`, not `api/src/...`).
- **Commits and pull requests made in this repository** record the
  integration work and everything after it. The first is
  `c67d9bd chore: initialize ParcelPulse engineering monorepo`.

Nothing in the imported history was reviewed in a pull request, because the
source repositories had no remote. It was not turned into pull requests
after the fact.

## Imports

Each component was imported with `git subtree add --prefix=<dir>`, without
squashing. That creates one merge commit per component whose second parent is
the source repository's HEAD.

| Component | Directory | Source HEAD (`main`)                       | Import merge | Pull request | Merged as |
| --------- | --------- | ------------------------------------------ | ------------ | ------------ | --------- |
| API       | `api/`    | `7f5be87dd822f757f778446f9605d307cb0233d2` | `83c6ef2`    | #21          | `a1fb97f` |
| Web       | `web/`    | `8dff66596147376db4d73a680c4c0f4a600f7d07` | `7014955`    | #22          | `a0b8542` |
| Worker    | `worker/` | `8d17a8ecf41551bae1b80e568f382f95f2246dce` | `dd52817`    | #23          | `43b2f7f` |
| Infra     | `infra/`  | `e7f30c72c31e9a493da075513c4f5a9e848d00a5` | `02e14a2`    | #24          | `a63110d` |

Verified for each import, and recorded in its pull request: the source HEAD is
an ancestor of `main`; the directory's tree was identical to the source HEAD's
tree at the import merge; author, committer and both dates of the imported
commits are identical to the source.

### What was changed at import

One commit per component, after the import merge, with only what the new
location required:

| Component | Commit    | Change                                                                        |
| --------- | --------- | ----------------------------------------------------------------------------- |
| API       | `c5a6d2b` | README note. No source, test, migration or configuration change               |
| Web       | `9f63ec0` | README note. No source, test or configuration change                          |
| Worker    | `6c0e37d` | README note. No source, test or configuration change                          |
| Infra     | `67fe207` | Compose build contexts, `.env.example` and the static Compose test point at `../api`, `../worker`, `../web`. No behaviour change |

### What was not imported

- **`workspace-tools`** had no Git history. It was an unversioned directory
  next to the four repositories. Its scripts entered version control in #25
  as new files, adapted to this layout.
- **`github-bootstrap.ps1`** and its data (a planned backlog of 25 issues for
  four separate GitHub repositories) were not carried over. The script had
  only been run as a dry run. The still-relevant open items were recreated as
  issues in this repository.
- **The component CI workflows** (`.github/workflows/ci.yml` in each source
  repository) had never executed. They were replaced by root workflows in #26,
  which is the first time any ParcelPulse CI ran.

## Later integration work

| Pull request | What                                                        | Merged as |
| ------------ | ----------------------------------------------------------- | --------- |
| #25          | Workspace tooling under version control                     | `7ee7be1` |
| #26          | Root CI: API, web, worker, infra and full-stack workflows   | `735b286` |

Pull requests after these are in the repository's pull request list.

## How the integration pull requests were handled

They were opened and merged by the same GitHub account, with merge commits.
None has a review approval: there was no second person, and GitHub does not
let an account approve its own pull request. Validation results are in each
pull request's description and comments.

Pull requests #21 to #25 were merged without any CI run, because no workflow
existed at the repository root until #26. Their validation was run locally and
reported in the pull request. From #26 on, CI runs on GitHub.

## Reading a file's history

Path-limited `git log` does not cross an import merge by default, because the
file had a different path before it.

| Command                                                  | Shows                                  |
| -------------------------------------------------------- | -------------------------------------- |
| `git log -- api/<file>`                                  | History since the import only          |
| `git log --follow -- api/<file>`                         | Nothing before the import              |
| `git log --follow -m -- api/<file>`                      | The original commits as well           |
| `git log --full-history -- <path before the import>`     | The original commits                   |
| `git blame api/<file>`                                   | The original commits, line by line     |
| `git log 7f5be87`                                        | The API's original history on its own  |

The same applies to `web/`, `worker/` and `infra/` with their source HEADs
from the table above.

## Documents inside the imported history

Documents as they appear in imported commits describe the four-repository
layout: they refer to `parcelpulse-api/docs/...`, tell the reader to check out
four repositories, and describe a release as four tags. That was accurate
when they were written. The current versions were updated for this repository
in the pull request that added this paragraph; the old wording remains in the
history and was not rewritten.

A v0.1.0 release was prepared in the four-repository layout (changelogs and
release notes exist in the imported history) but never tagged. No tag exists
in any source repository.
