# Load testing webhook ingestion

`infra/loadtest/webhook_load.py` is a basic load test for `POST /webhooks/carrier`,
the endpoint that takes traffic we do not control. This page describes the
method and records the first observations. It makes no capacity claim.

## What the script does

1. **Setup (not measured).** Registers `--shipments` shipments through the API.
2. **Measured phase.** Builds a complete seven-event journey for every
   shipment, signs each webhook, and delivers them from `--concurrency` threads,
   each with its own keep-alive connection. Optionally repeats a share of the
   events (`--duplicate-ratio`) and shuffles the delivery order (`--shuffle`).
   Each request is timed from just before it is written to after the response
   body has been read.
3. **Correctness check (not measured).** Reads every shipment back. The run
   only counts as OK if every request was accepted, every shipment is
   `DELIVERED` with exactly seven stored events, and the numbers of
   `PROCESSED` and `DUPLICATE` results equal the numbers of distinct events and
   repeats that were sent.

A run that is fast but fails the correctness check is a failed run.

It reports request count, results, wall time, throughput (requests divided by
the wall time of the measured phase) and latency (min, mean, p50, p95, p99,
max). `--json` writes all of it, with the parameters and client platform, to a
file.

The shipments have no notification email, so the run measures ingestion only:
no notifications are created and the worker is idle.

## Running it

Inside the Compose network (recommended), from `infra/`:

```powershell
docker compose run --rm loadtest --shipments 100 --concurrency 16 --duplicate-ratio 0.25 --shuffle
```

From the host, from `infra/`:

```powershell
py -3.12 loadtest\webhook_load.py --shipments 100 --concurrency 16 --duplicate-ratio 0.25 --shuffle
```

Each run uses fresh tracking numbers and can be repeated against the same
stack. The data it creates stays in the database; `docker compose down -v`
removes it.

## Where to run the load generator

Run it inside the Compose network when the numbers matter. On Docker Desktop
for Windows, a request from the host to a published port passes through
Docker's port forwarding, and we observed that this adds roughly 45 ms to
every request that has a body. The API's own request log showed the same
delay, because the server is waiting for the body to arrive. The effect
disappears when the generator runs next to the API:

| Generator location | Serial p50 (concurrency 1) |
| ------------------ | -------------------------- |
| Windows host, through the published port | 52 ms |
| Container on the Compose network         | 5.0 ms |

Host-side numbers are therefore a measurement of Docker Desktop's networking
as much as of ParcelPulse.

## First observations (2026-09-30)

One run of each configuration, on a developer laptop, with the load generator,
API, PostgreSQL and everything else sharing the same machine. They are data
points for comparison with later runs on the same setup, not a statement of
what the system can handle.

Setup: Intel Core i7-13650HX (20 logical processors), 16 GB RAM, Windows 11,
Docker Desktop (WSL 2 backend, 8 GB assigned to Docker). API source as
of commit `8e364c4`: one uvicorn process, default SQLAlchemy connection pool (5
connections plus 10 overflow), PostgreSQL 17.11 with default settings.
Generator: `python:3.12-slim` container on the Compose network.

| Shipments | Webhooks | Concurrency | Duplicates | Shuffled | Throughput | p50    | p95    | p99    | Correct |
| --------- | -------- | ----------- | ---------- | -------- | ---------- | ------ | ------ | ------ | ------- |
| 30        | 210      | 1           | 0          | no       | 195 req/s  | 5.0 ms | 6.2 ms | 6.8 ms | yes     |
| 100       | 875      | 16          | 25 %       | yes      | 164 req/s  | 95 ms  | 130 ms | 153 ms | yes     |

What these two runs show:

- Correctness held under concurrent, shuffled delivery with duplicates: 700
  events processed once, 175 duplicates recognised, all shipments `DELIVERED`.
- Throughput did **not** increase with concurrency; at 16 connections it was
  lower than serial and latency rose about twentyfold. The API process, not
  the client, is the limit in this setup. We have not profiled why. Candidates
  to examine: the single worker process and the GIL, the synchronous endpoint
  running in a thread pool, the connection pool being smaller than the
  concurrency, and row-lock contention when several events for one shipment
  arrive together.

## Not covered yet

- Runs long enough to show steady-state behaviour, growth of the tables, or
  the effect of the notification path.
- More than one API process or replica.
- Isolation between the generator and the system under test.
- Repeated runs with variance.
- Any target or pass/fail threshold. There is no performance requirement yet
  to test against.
