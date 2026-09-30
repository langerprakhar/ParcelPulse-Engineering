# Engineering history

ParcelPulse was first developed as four independent Git repositories, one per
component, each with its own history:

| Source repository    | Component                                         |
| -------------------- | ------------------------------------------------- |
| `parcelpulse-api`    | FastAPI service                                   |
| `parcelpulse-web`    | Next.js dashboard                                 |
| `parcelpulse-worker` | Notification worker and sweeper                   |
| `parcelpulse-infra`  | Compose stack, carrier simulator, system documentation |

This repository, `ParcelPulse-Engineering`, was created afterwards to be the
single canonical repository for the project. The components are brought in one
at a time, each through its own pull request, with their original commits
preserved.

Two kinds of history therefore exist side by side here and should not be
confused:

- **Imported commits** are the original development history of a component,
  written before this repository existed.
- **Commits and pull requests made in this repository** record the integration
  work and everything after it.

## Imports

Each import adds a row in the pull request that performs it.

| Component | Directory | Source repository | Source commit (HEAD of `main`)             | Commits | Issue |
| --------- | --------- | ----------------- | ------------------------------------------ | ------- | ----- |
| API       | `api/`    | `parcelpulse-api` | `7f5be87dd822f757f778446f9605d307cb0233d2` | 10      | #1    |
| Web       | `web/`    | `parcelpulse-web` | `8dff66596147376db4d73a680c4c0f4a600f7d07` | 11      | #2    |
