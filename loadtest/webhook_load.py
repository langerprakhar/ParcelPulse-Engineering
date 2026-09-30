#!/usr/bin/env python3
"""Basic load test for carrier webhook ingestion.

Registers a set of shipments, then delivers a complete, signed journey for each
one to POST /webhooks/carrier from a pool of concurrent connections. Optionally
shuffles the delivery order and repeats a share of the events, the way carriers
do. Afterwards it reads every shipment back and checks that the load did not
corrupt anything: each must be DELIVERED with exactly one stored event per
carrier event.

    python loadtest/webhook_load.py --shipments 100 --concurrency 16
    python loadtest/webhook_load.py --shipments 200 --duplicate-ratio 0.3 --shuffle --json out.json

Uses only the Python standard library. The signing secret is read from
--secret or WEBHOOK_SIGNING_SECRET and defaults to the local Compose value.

See docs/load-testing.md for the methodology and how to read the output.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import json
import os
import platform
import random
import statistics
import sys
import threading
import time
import urllib.parse
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

LOCAL_DEVELOPMENT_SECRET = "local-development-only-webhook-secret"

# (event type, hours after the start of the journey)
JOURNEY = [
    ("LABEL_CREATED", 0),
    ("IN_TRANSIT", 4),
    ("AT_DISTRIBUTION_CENTER", 20),
    ("IN_TRANSIT", 28),
    ("AT_DISTRIBUTION_CENTER", 40),
    ("OUT_FOR_DELIVERY", 44),
    ("DELIVERED", 50),
]


@dataclass(frozen=True)
class Sample:
    status: int | None
    result: str
    seconds: float


class Client:
    """One keep-alive connection per thread."""

    def __init__(self, base_url: str, timeout: float) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._https = parsed.scheme == "https"
        self._timeout = timeout
        self._local = threading.local()

    def _connection(self) -> http.client.HTTPConnection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            factory = http.client.HTTPSConnection if self._https else http.client.HTTPConnection
            connection = factory(self._host, self._port, timeout=self._timeout)
            self._local.connection = connection
        return connection

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        *,
        reconnect: bool = False,
    ) -> tuple[int, bytes]:
        """Send one request.

        ``reconnect`` retries once on a fresh connection. The setup and
        verification phases use it because the server closes keep-alive
        connections that sat idle; the measured phase does not, so that a
        dropped request is counted as a failure rather than hidden.
        """
        try:
            connection = self._connection()
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        except (OSError, http.client.HTTPException):
            # Drop the broken connection so the next request reconnects.
            self._local.connection = None
            if reconnect:
                return self.request(method, path, body, headers)
            raise


def sign(secret: str, body: bytes) -> str:
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def build_events(tracking_numbers: list[str], carrier: str) -> list[bytes]:
    """One JSON body per carrier event, for every shipment."""
    journey_length = timedelta(hours=JOURNEY[-1][1])
    started_at = datetime.now(UTC) - journey_length - timedelta(hours=2)
    bodies = []
    for tracking_number in tracking_numbers:
        for event_type, offset in JOURNEY:
            payload = {
                "provider": carrier,
                "event_id": f"load_{uuid.uuid4().hex}",
                "tracking_number": tracking_number,
                "event_type": event_type,
                "occurred_at": (started_at + timedelta(hours=offset)).isoformat(),
                "location": {"city": "Loadtest", "country": "GB"},
            }
            bodies.append(json.dumps(payload, separators=(",", ":")).encode())
    return bodies


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round(fraction * (len(sorted_values) - 1))))
    return sorted_values[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"))
    parser.add_argument(
        "--secret", default=os.environ.get("WEBHOOK_SIGNING_SECRET", LOCAL_DEVELOPMENT_SECRET)
    )
    parser.add_argument("--carrier", default="simcarrier")
    parser.add_argument("--shipments", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--duplicate-ratio",
        type=float,
        default=0.0,
        help="Share of events delivered a second time (0.0 to 1.0)",
    )
    parser.add_argument("--shuffle", action="store_true", help="Deliver events in random order")
    parser.add_argument("--seed", type=int, default=1, help="Seed for shuffling and duplicates")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--json", metavar="PATH", help="Also write the results to this file")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    client = Client(args.api_url, args.timeout)
    run_id = uuid.uuid4().hex[:8].upper()
    tracking_numbers = [f"LT{run_id}{index:06d}" for index in range(args.shipments)]

    # --- Setup (not measured) -------------------------------------------------
    print(f"Registering {args.shipments} shipments (run {run_id}) ...")
    shipment_ids: dict[str, str] = {}
    for tracking_number in tracking_numbers:
        body = json.dumps({"tracking_number": tracking_number, "carrier": args.carrier}).encode()
        status, raw = client.request(
            "POST", "/shipments", body, {"Content-Type": "application/json"}, reconnect=True
        )
        if status != 201:
            print(f"could not register {tracking_number}: HTTP {status} {raw[:200]!r}")
            return 2
        shipment_ids[tracking_number] = json.loads(raw)["id"]

    events = build_events(tracking_numbers, args.carrier)
    duplicates = rng.sample(events, k=round(len(events) * args.duplicate_ratio))
    deliveries = events + duplicates
    if args.shuffle:
        rng.shuffle(deliveries)

    # --- Measured phase -------------------------------------------------------
    def deliver(body: bytes) -> Sample:
        headers = {
            "Content-Type": "application/json",
            "X-Carrier-Signature": sign(args.secret, body),
        }
        started = time.perf_counter()
        try:
            status, raw = client.request("POST", "/webhooks/carrier", body, headers)
        except (OSError, http.client.HTTPException) as error:
            return Sample(None, type(error).__name__, time.perf_counter() - started)
        elapsed = time.perf_counter() - started
        try:
            parsed: Any = json.loads(raw)
            result = parsed.get("result") or parsed.get("error", {}).get("code") or "unknown"
        except ValueError:
            result = "non_json_response"
        return Sample(status, result, elapsed)

    print(
        f"Delivering {len(deliveries)} webhooks "
        f"({len(events)} events + {len(duplicates)} duplicates) "
        f"with {args.concurrency} concurrent connections ..."
    )
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        samples = list(pool.map(deliver, deliveries))
    wall_seconds = time.perf_counter() - started

    # --- Correctness check (not measured) ------------------------------------
    print("Verifying shipment state ...")
    wrong_status, wrong_event_count = [], []
    for tracking_number, shipment_id in shipment_ids.items():
        _, raw = client.request("GET", f"/shipments/{shipment_id}", reconnect=True)
        if json.loads(raw)["current_status"] != "DELIVERED":
            wrong_status.append(tracking_number)
        _, raw = client.request("GET", f"/shipments/{shipment_id}/events?limit=1", reconnect=True)
        if json.loads(raw)["total"] != len(JOURNEY):
            wrong_event_count.append(tracking_number)

    # --- Report ---------------------------------------------------------------
    latencies = sorted(sample.seconds * 1000 for sample in samples)
    results = Counter(sample.result for sample in samples)
    statuses = Counter(str(sample.status) for sample in samples)
    accepted = sum(1 for sample in samples if sample.status == 200)
    summary = {
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "parameters": {
            "api_url": args.api_url,
            "shipments": args.shipments,
            "events_per_shipment": len(JOURNEY),
            "concurrency": args.concurrency,
            "duplicate_ratio": args.duplicate_ratio,
            "shuffle": args.shuffle,
            "seed": args.seed,
        },
        "client": {"python": platform.python_version(), "platform": platform.platform()},
        "requests": len(samples),
        "accepted": accepted,
        "failed": len(samples) - accepted,
        "http_statuses": dict(statuses),
        "results": dict(results),
        "wall_seconds": round(wall_seconds, 3),
        "requests_per_second": round(len(samples) / wall_seconds, 1),
        "latency_ms": {
            "min": round(latencies[0], 2),
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "p99": round(percentile(latencies, 0.99), 2),
            "max": round(latencies[-1], 2),
        },
        "correctness": {
            "shipments_not_delivered": len(wrong_status),
            "shipments_with_wrong_event_count": len(wrong_event_count),
            "unexpected_processed_count": results.get("PROCESSED", 0) != len(events),
            "unexpected_duplicate_count": results.get("DUPLICATE", 0) != len(duplicates),
        },
    }
    correct = not any(summary["correctness"].values()) and accepted == len(samples)

    print()
    print(f"requests            {summary['requests']} ({accepted} accepted)")
    print(f"results             {dict(results)}")
    print(f"wall time           {summary['wall_seconds']} s")
    print(f"throughput          {summary['requests_per_second']} requests/s")
    latency = summary["latency_ms"]
    print(
        "latency (ms)        "
        f"min {latency['min']}  mean {latency['mean']}  p50 {latency['p50']}  "
        f"p95 {latency['p95']}  p99 {latency['p99']}  max {latency['max']}"
    )
    print(f"correctness         {'OK' if correct else 'FAILED ' + str(summary['correctness'])}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
    return 0 if correct else 1


if __name__ == "__main__":
    sys.exit(main())
