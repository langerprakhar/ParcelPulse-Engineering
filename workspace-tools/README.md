# workspace-tools

PowerShell utilities for working with ParcelPulse as a whole: start and stop the
stack, verify every component, run the end-to-end smoke test.

They expect to live at the root of this repository, next to `api/`, `web/`,
`worker/` and `infra/`, and run in Windows PowerShell 5.1 and PowerShell 7. If
script execution is disabled, run them as
`powershell -ExecutionPolicy Bypass -File .\<script>.ps1`.

| Script                | What it does                                                                 |
| --------------------- | ---------------------------------------------------------------------------- |
| `start-all.ps1`       | Builds and starts the whole stack and waits until it is healthy. `-Fresh` rebuilds the database from zero |
| `stop-all.ps1`        | Stops the stack. `-RemoveData` also deletes the database and queue volumes   |
| `smoke-test.ps1`      | Runs the end-to-end smoke test against the running stack                     |
| `verify-all.ps1`      | Runs every lint, type, test and build check of every component, each reported separately. `-Setup` installs dependencies first, `-Smoke` adds the smoke test |
| `slack-bootstrap.ps1` | Creates the missing Slack channels (needs `SLACK_BOT_TOKEN`)                 |
| `common.ps1`          | Helpers shared by the scripts above                                          |

`Get-Help .\<script>.ps1 -Full` shows each script's parameters and exit codes.

## Typical use

```powershell
cd workspace-tools
.\verify-all.ps1 -Setup     # first time: create virtual environments, npm ci, run all checks
.\start-all.ps1             # start the stack
.\smoke-test.ps1            # verify it end to end
.\stop-all.ps1              # stop it
```

## Results and logs

`verify-all.ps1` prints one line per check with `PASS`, `FAIL`, `BLOCKED` (a
required tool or file is missing) or `SKIPPED` (you asked for it), and exits
non-zero unless everything passed. The output of every check and a
`summary.csv` are written to `logs\verify-<timestamp>\`, which Git ignores.

A check that could not run is never reported as passed.

## Where these came from

These scripts were written alongside the four original ParcelPulse
repositories and sat in an unversioned directory next to them, because they
belonged to none of them. They entered version control with this repository,
adapted to its directory names. They have no earlier Git history.

One script was not carried over: `github-bootstrap.ps1`, which created four
separate GitHub repositories with labels, milestones and a backlog. It has no
purpose in a single repository and was only ever run as a dry run.

## Slack

`slack-bootstrap.ps1` needs `SLACK_BOT_TOKEN` in the environment and does
nothing, and says what is missing, without it. See `infra\slack\README.md`.
It never prints, logs or stores the token.
