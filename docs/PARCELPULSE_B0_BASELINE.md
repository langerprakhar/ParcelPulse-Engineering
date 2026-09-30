# PARCELPULSE BASELINE B0

**Recorded:** 2026-09-30 15:56 UTC  
**Canonical repository:** [langerprakhar/ParcelPulse-Engineering](https://github.com/langerprakhar/ParcelPulse-Engineering)  
**Baseline commit (`main` at release):** `250ab8bf3197f7fd2874a598e080f7a0ab6a0f38`  
**Release:** `v0.1.0`  
**Release commit:** `250ab8bf3197f7fd2874a598e080f7a0ab6a0f38`

This record was added after the release tag. The B0 documentation commit is later than the release commit and is not part of the `v0.1.0` release artifact. The annotated tag was not moved or recreated.

## Repository and tag state

- Canonical branch: `main`; at capture, local `main` and `origin/main` both resolved to `250ab8bf3197f7fd2874a598e080f7a0ab6a0f38` and the working tree was clean.
- `v0.1.0` is an annotated tag. Tag object: `3bc958f3887f0a3bfb03eeae8af3cb8676b554c9`; it directly references release commit `250ab8bf3197f7fd2874a598e080f7a0ab6a0f38`.
- GitHub Release [ParcelPulse v0.1.0](https://github.com/langerprakhar/ParcelPulse-Engineering/releases/tag/v0.1.0) is published, not a draft or prerelease (published 2026-09-30 15:39:51 UTC).
- Deployment status: **NOT DEPLOYED**. The release validates the local Docker Compose stack only.
- Slack status: **NOT YET CONFIGURED**; no real Slack workspace bootstrap has run.
- Marrow integration: **NONE**.

## Imported source repositories

All four source HEAD commits are ancestors of canonical `main`, retained with their original commit identities and histories. The four original local source worktrees were clean at capture, each on `main` at its baseline SHA. The engineering history records that these source repositories were local-only and had no remotes; they were not modified by this bootstrap continuation.

| Component | Original source repository | Baseline HEAD |
| --- | --- | --- |
| API | `parcelpulse-api` | `7f5be87dd822f757f778446f9605d307cb0233d2` |
| Web | `parcelpulse-web` | `8dff66596147376db4d73a680c4c0f4a600f7d07` |
| Worker | `parcelpulse-worker` | `8d17a8ecf41551bae1b80e568f382f95f2246dce` |
| Infra | `parcelpulse-infra` | `e7f30c72c31e9a493da075513c4f5a9e848d00a5` |

## Integration pull requests

All integration PRs below were merged normally. Merge SHAs are the recorded GitHub merge commits.

| PR | Change | Merge SHA |
| --- | --- | --- |
| [#21](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/21) | API history and component | `a1fb97ffedc94f949d6815313a4bbcca0c5802a8` |
| [#22](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/22) | Web history and component | `a0b85427e53601ee128b1d68c6e3d4f46692da90` |
| [#23](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/23) | Worker history and component | `43b2f7fbb9f0f4a789f3aaeef416aec6818afe5d` |
| [#24](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/24) | Infra history and component | `a63110dc804aa80fd68144582ae05e69b0b750fa` |
| [#25](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/25) | Canonical workspace tooling | `7ee7be1ebbaa4e440c18862cde4bcaa5dfa91e56` |
| [#26](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/26) | Root monorepo CI | `735b286aebdb2776acb3344e017285983d5d2ea4` |
| [#27](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/27) | System documentation | `3e4cc651c4a208e226ff97214c01d8014c50d41b` |
| [#28](https://github.com/langerprakhar/ParcelPulse-Engineering/pull/28) | v0.1.0 release notes | `250ab8bf3197f7fd2874a598e080f7a0ab6a0f38` |

## Validation evidence

### Clean clone

Validation was run from a fresh GitHub clone on `250ab8bf3197f7fd2874a598e080f7a0ab6a0f38` using:

```powershell
workspace-tools\verify-all.ps1 -Setup -Smoke
```

Result: **54 passed, 0 failed, 0 blocked, 0 skipped** (7 setup steps and 47 checks). The clean-clone report in closed issue [#7](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/7) records:

| Area | Observed result |
| --- | ---: |
| API | 182 tests passed |
| Worker | 82 tests passed |
| Web | 94 tests passed |
| Carrier simulator | 53 tests passed |
| Compose static checks | 24 passed |
| Smoke checks | 46/46 passed |
| Headless browser checks | 20/20 passed |

The stack started from empty volumes, applied migrations `0001`–`0003`, and passed smoke checks both inside the Compose network and through host-published ports. Duplicate webhook handling, notification idempotency, and late out-of-order events were verified. The dashboard was exercised against the real API.

### GitHub Actions on the release commit

Each run completed with conclusion `success` and `head_sha` equal to `250ab8bf3197f7fd2874a598e080f7a0ab6a0f38`:

| Workflow | Run | Status |
| --- | ---: | --- |
| API CI | [36736774784](https://github.com/langerprakhar/ParcelPulse-Engineering/actions/runs/36736774784) | completed / success |
| Web CI | [36736778888](https://github.com/langerprakhar/ParcelPulse-Engineering/actions/runs/36736778888) | completed / success |
| Worker CI | [36736783493](https://github.com/langerprakhar/ParcelPulse-Engineering/actions/runs/36736783493) | completed / success |
| Infra CI | [36736788408](https://github.com/langerprakhar/ParcelPulse-Engineering/actions/runs/36736788408) | completed / success |
| Full-stack CI | [36736793228](https://github.com/langerprakhar/ParcelPulse-Engineering/actions/runs/36736793228) | completed / success; 46/46 smoke checks |

These were manually dispatched on the release commit. The previous main commit's API, Web, Worker, and Infra runs were cancelled when these started because the current concurrency setting cancels earlier runs; this behavior is tracked in issue #29.

## Known limitations and open engineering work

At the B0 release baseline, these future-work issues remain open:

- [#10](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/10) Worker crash window can permit duplicate notification delivery.
- [#11](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/11) A maintained browser end-to-end suite is not present.
- [#12](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/12) Authentication and access control are not implemented; do not expose shipment endpoints publicly.
- [#13](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/13) No real carrier integration; only the simulator is supported.
- [#14](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/14) Webhook receipts and notifications have no retention cleanup.
- [#15](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/15) Failed notifications have no dead-letter reprocessing path.
- [#17](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/17) Webhook throughput did not scale with concurrency in the recorded load test; cause is unknown, and that load test was not rerun for B0.
- [#18](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/18) OpenAPI contract publication and versioning remain future work; component contracts are mirrored by hand.
- [#19](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/19) Slack app and project channels are not configured.
- [#20](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/20) No hosted deployment or beta environment exists.
- [#29](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/29) New main runs can cancel prior main runs before completion.
- [#30](https://github.com/langerprakhar/ParcelPulse-Engineering/issues/30) CI reports deprecated Node.js 20 action and `ubuntu-latest` migration warnings.

Further release limitations include terminal shipment states not being corrected by later events, estimates coming from the carrier rather than ParcelPulse, English-only email notifications, and no second-person PR approvals in this single-account workflow.

## Scope boundary

B0 records the verified v0.1.0 engineering baseline only. It does not claim deployment, Slack setup, Marrow integration, or completion of the open engineering work listed above.
