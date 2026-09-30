#!/usr/bin/env python3
"""End-to-end smoke test for a running ParcelPulse stack.

Drives the real services over HTTP: the carrier simulator sends signed webhooks
to the API, the worker delivers notifications to the mail sink, and the checks
read the results back through the public API, the mail sink and the web UI.

    python tests/smoke/smoke_test.py
    python tests/smoke/smoke_test.py --api-url http://localhost:8000 --json report.json

Uses only the Python standard library. Exits 0 when every check passes and 1
otherwise. Each run creates its own shipment and email address, so it can be
repeated against the same stack.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

TIMEOUT_SECONDS = 15


@dataclass
class Response:
    status: int
    body: Any
    text: str


def http(
    method: str, url: str, body: Any = None, headers: dict[str, str] | None = None
) -> Response:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
            status, raw = reply.status, reply.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return Response(status=status, body=parsed, text=text)


@dataclass
class Check:
    step: str
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def check(self, step: str, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append(Check(step, name, passed, detail))
        marker = "PASS" if passed else "FAIL"
        suffix = f"  [{detail}]" if detail and not passed else ""
        print(f"  {marker}  {name}{suffix}")
        return passed

    @property
    def failed(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]


class Stack:
    def __init__(self, args: argparse.Namespace) -> None:
        self.api = args.api_url.rstrip("/")
        self.web = args.web_url.rstrip("/")
        self.simulator = args.simulator_url.rstrip("/")
        self.mail = args.mail_url.rstrip("/")

    # --- ParcelPulse API ----------------------------------------------------

    def shipment(self, shipment_id: str) -> dict[str, Any]:
        return http("GET", f"{self.api}/shipments/{shipment_id}").body

    def timeline(self, shipment_id: str) -> list[dict[str, Any]]:
        return http("GET", f"{self.api}/shipments/{shipment_id}/events?limit=100").body["items"]

    def notifications(self, shipment_id: str) -> list[dict[str, Any]]:
        reply = http("GET", f"{self.api}/shipments/{shipment_id}/notifications?limit=100")
        return reply.body["items"]

    def receipts(self, provider_event_id: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"provider_event_id": provider_event_id})
        return http("GET", f"{self.api}/dev/webhook-receipts?{query}").body["items"]

    # --- Carrier simulator --------------------------------------------------

    def simulate(self, tracking_number: str, operation: str, body: Any = None) -> dict[str, Any]:
        reply = http("POST", f"{self.simulator}/shipments/{tracking_number}/{operation}", body)
        if reply.status != 200:
            raise RuntimeError(f"simulator {operation} failed: HTTP {reply.status} {reply.text}")
        return reply.body

    # --- Mail sink ----------------------------------------------------------

    def emails_to(self, address: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"query": f'to:"{address}"'})
        return http("GET", f"{self.mail}/api/v1/search?{query}").body.get("messages") or []


def wait_for(predicate: Any, timeout: float = 30.0, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


def results_of(operation: dict[str, Any]) -> list[str]:
    return [delivery["result"] for delivery in operation["deliveries"]]


def run(stack: Stack, report: Report) -> None:
    run_id = uuid.uuid4().hex[:10].upper()
    tracking_number = f"SM{run_id}"
    email = f"smoke-{run_id.lower()}@example.com"
    print(f"Smoke run {run_id}: shipment {tracking_number}, notifications to {email}\n")

    # ------------------------------------------------------------------ health
    step = "health"
    print("Health and readiness")
    for name, url, expected in [
        ("API liveness", f"{stack.api}/health", "ok"),
        ("API readiness (PostgreSQL and Redis)", f"{stack.api}/ready", "ready"),
        ("Web liveness", f"{stack.web}/api/health", "ok"),
        ("Web readiness (web can reach a ready API)", f"{stack.web}/api/ready", "ready"),
        ("Carrier simulator liveness", f"{stack.simulator}/health", "ok"),
    ]:
        reply = http("GET", url)
        status = (reply.body or {}).get("status") if isinstance(reply.body, dict) else None
        report.check(step, name, reply.status == 200 and status == expected, f"HTTP {reply.status}")
    reply = http("GET", f"{stack.mail}/api/v1/info")
    report.check(step, "Mail sink reachable", reply.status == 200, f"HTTP {reply.status}")

    # ------------------------------------------------------- 1. create shipment
    step = "create"
    print("\n1. Create a shipment")
    created = http(
        "POST",
        f"{stack.api}/shipments",
        {"tracking_number": tracking_number, "carrier": "simcarrier", "notification_email": email},
    )
    report.check(step, "POST /shipments returns 201", created.status == 201, created.text[:200])
    shipment_id = created.body["id"]
    report.check(
        step, "New shipment starts as CREATED", created.body["current_status"] == "CREATED"
    )
    by_tracking = http("GET", f"{stack.api}/shipments/by-tracking/{tracking_number.lower()}")
    report.check(
        step,
        "Lookup by tracking number finds it",
        by_tracking.status == 200 and by_tracking.body["id"] == shipment_id,
    )
    again = http(
        "POST",
        f"{stack.api}/shipments",
        {"tracking_number": tracking_number, "carrier": "simcarrier"},
    )
    report.check(
        step, "Registering it twice returns 409", again.status == 409, f"HTTP {again.status}"
    )

    simulated = http("POST", f"{stack.simulator}/shipments", {"tracking_number": tracking_number})
    report.check(step, "Carrier simulator plans its journey", simulated.status == 201)

    # ---------------------------------------------------- 2-3. events, timeline
    step = "events"
    print("\n2. Send carrier events   3. Verify the API timeline")
    sent = stack.simulate(tracking_number, "advance", {"count": 3})
    report.check(
        step,
        "Three webhooks accepted as PROCESSED",
        results_of(sent) == ["PROCESSED"] * 3,
        str(results_of(sent)),
    )
    timeline = stack.timeline(shipment_id)
    report.check(
        step,
        "Timeline lists the three events in carrier-time order",
        [event["event_type"] for event in timeline]
        == ["LABEL_CREATED", "IN_TRANSIT", "AT_DISTRIBUTION_CENTER"],
        str([event["event_type"] for event in timeline]),
    )
    report.check(
        step,
        "Each event keeps event_at and received_at separately",
        all(
            datetime.fromisoformat(event["received_at"]) > datetime.fromisoformat(event["event_at"])
            for event in timeline
        ),
    )
    report.check(
        step,
        "Events carry their location",
        all((event["location"] or {}).get("city") for event in timeline),
    )
    shipment = stack.shipment(shipment_id)
    report.check(
        step,
        "Shipment status is AT_DISTRIBUTION_CENTER",
        shipment["current_status"] == "AT_DISTRIBUTION_CENTER",
        shipment["current_status"],
    )
    report.check(
        step,
        "Carrier-provided delivery estimate is stored",
        shipment["estimated_delivery_at"] is not None,
    )

    # ------------------------------------------------------ 4-5. duplicate webhook
    step = "duplicate"
    print("\n4. Send a duplicate webhook   5. Verify no duplicate event")
    last_event_id = sent["deliveries"][-1]["event_id"]
    before = stack.shipment(shipment_id)
    duplicate = stack.simulate(tracking_number, "duplicate", {"count": 2})
    report.check(
        step,
        "Redelivered webhooks are acknowledged as DUPLICATE",
        results_of(duplicate) == ["DUPLICATE", "DUPLICATE"],
        str(results_of(duplicate)),
    )
    report.check(step, "Timeline still has three events", len(stack.timeline(shipment_id)) == 3)
    report.check(
        step, "Shipment is unchanged by the duplicates", stack.shipment(shipment_id) == before
    )
    receipts = stack.receipts(last_event_id)
    report.check(
        step,
        "Receipts record 1 processed and 2 duplicate deliveries of the event",
        [receipt["result"] for receipt in receipts] == ["PROCESSED", "DUPLICATE", "DUPLICATE"]
        and len({receipt["tracking_event_id"] for receipt in receipts}) == 1,
        str([receipt["result"] for receipt in receipts]),
    )

    # ------------------------------------------------- 6-7. notification exactly once
    step = "notification"
    print("\n6. Trigger a notification   7. Verify it happened exactly once")
    held = http("POST", f"{stack.simulator}/shipments/{tracking_number}/hold").body["held"]
    report.check(
        step,
        "Carrier withholds the next event (IN_TRANSIT) for later",
        [event["event_type"] for event in held] == ["IN_TRANSIT"],
    )
    onward = stack.simulate(tracking_number, "advance", {"count": 2})
    report.check(
        step,
        "AT_DISTRIBUTION_CENTER and OUT_FOR_DELIVERY are processed",
        [delivery["event_type"] for delivery in onward["deliveries"]]
        == ["AT_DISTRIBUTION_CENTER", "OUT_FOR_DELIVERY"]
        and results_of(onward) == ["PROCESSED", "PROCESSED"],
    )
    report.check(
        step,
        "Shipment status is OUT_FOR_DELIVERY",
        stack.shipment(shipment_id)["current_status"] == "OUT_FOR_DELIVERY",
    )

    def out_for_delivery_sent() -> bool:
        notifications = stack.notifications(shipment_id)
        return len(notifications) == 1 and notifications[0]["status"] == "SENT"

    report.check(
        step,
        "Worker delivers the OUT_FOR_DELIVERY notification (status SENT)",
        wait_for(out_for_delivery_sent),
        str(stack.notifications(shipment_id)),
    )
    report.check(
        step,
        "Mail sink received it",
        wait_for(lambda: len(stack.emails_to(email)) == 1, timeout=15),
        f"{len(stack.emails_to(email))} messages",
    )

    # The carrier now retries the very event that caused the notification.
    retried = stack.simulate(tracking_number, "duplicate", {"count": 3})
    report.check(
        step,
        "Three retries of the OUT_FOR_DELIVERY webhook are DUPLICATE",
        results_of(retried) == ["DUPLICATE"] * 3,
    )
    # Give a wrongly created notification time to be delivered before counting.
    time.sleep(3)
    notifications = stack.notifications(shipment_id)
    report.check(
        step,
        "Still exactly one notification row, attempted once",
        len(notifications) == 1
        and notifications[0]["type"] == "OUT_FOR_DELIVERY"
        and notifications[0]["attempts"] == 1,
        str(notifications),
    )
    emails = stack.emails_to(email)
    report.check(
        step,
        "Still exactly one email in the mail sink",
        len(emails) == 1 and emails[0]["Subject"] == f"Out for delivery: {tracking_number}",
        str([message["Subject"] for message in emails]),
    )

    # ---------------------------------------------------- 8-9. out-of-order event
    step = "out-of-order"
    print("\n8. Send an out-of-order event   9. Verify the shipment state stays correct")
    late = stack.simulate(tracking_number, "release-held")
    report.check(
        step,
        "The late IN_TRANSIT event is accepted as a new event",
        results_of(late) == ["PROCESSED"] and late["deliveries"][0]["event_type"] == "IN_TRANSIT",
    )
    shipment = stack.shipment(shipment_id)
    report.check(
        step,
        "Shipment status is still OUT_FOR_DELIVERY (not moved backwards)",
        shipment["current_status"] == "OUT_FOR_DELIVERY",
        shipment["current_status"],
    )
    timeline = stack.timeline(shipment_id)
    types = [event["event_type"] for event in timeline]
    report.check(
        step,
        "Timeline has all six events in carrier-time order",
        types
        == [
            "LABEL_CREATED",
            "IN_TRANSIT",
            "AT_DISTRIBUTION_CENTER",
            "IN_TRANSIT",
            "AT_DISTRIBUTION_CENTER",
            "OUT_FOR_DELIVERY",
        ]
        and [event["event_at"] for event in timeline]
        == sorted(event["event_at"] for event in timeline),
        str(types),
    )
    late_event = next(
        event for event in timeline if event["id"] == _event_id(stack, late["deliveries"][0])
    )
    report.check(
        step,
        "The late event is flagged arrived_out_of_order and did not change the status",
        late_event["arrived_out_of_order"] is True and late_event["changed_status"] is False,
    )
    report.check(
        step,
        "It was received after the event that follows it in the timeline",
        late_event["received_at"] > timeline[timeline.index(late_event) + 1]["received_at"],
    )
    report.check(
        step,
        "last_event_at is still the OUT_FOR_DELIVERY time",
        shipment["last_event_at"] == timeline[-1]["event_at"],
    )
    time.sleep(2)
    report.check(
        step,
        "The late event produced no notification",
        len(stack.notifications(shipment_id)) == 1 and len(stack.emails_to(email)) == 1,
    )

    # ------------------------------------------------------------- delivery
    step = "delivery"
    print("\nFinish the journey")
    final = stack.simulate(tracking_number, "lifecycle", {"duplicates": 1})
    report.check(
        step,
        "DELIVERED is processed once and its retry is a duplicate",
        results_of(final) == ["PROCESSED", "DUPLICATE"],
        str(results_of(final)),
    )
    report.check(
        step,
        "Shipment status is DELIVERED",
        stack.shipment(shipment_id)["current_status"] == "DELIVERED",
    )

    def both_sent() -> bool:
        current = stack.notifications(shipment_id)
        return len(current) == 2 and all(item["status"] == "SENT" for item in current)

    report.check(step, "Two notifications in total, both SENT", wait_for(both_sent))
    report.check(
        step,
        "Two emails in total: out for delivery, then delivered",
        wait_for(lambda: len(stack.emails_to(email)) == 2, timeout=15)
        and sorted(message["Subject"] for message in stack.emails_to(email))
        == [f"Delivered: {tracking_number}", f"Out for delivery: {tracking_number}"],
        str([message["Subject"] for message in stack.emails_to(email)]),
    )

    # ------------------------------------------------------------- security
    step = "security"
    print("\nWebhook authentication")
    unsigned = http(
        "POST",
        f"{stack.api}/webhooks/carrier",
        {
            "provider": "simcarrier",
            "event_id": f"evt_forged_{run_id}",
            "tracking_number": tracking_number,
            "event_type": "RETURNED",
            "occurred_at": "2026-01-01T00:00:00Z",
        },
    )
    report.check(step, "Unsigned webhook is rejected with 401", unsigned.status == 401)
    report.check(
        step,
        "Forged event changed nothing",
        stack.shipment(shipment_id)["current_status"] == "DELIVERED"
        and len(stack.timeline(shipment_id)) == 7,
    )

    # ------------------------------------------------------------- 10. web
    step = "web"
    print("\n10. Web dashboard")
    page = http("GET", f"{stack.web}/shipments/{shipment_id}")
    report.check(
        step,
        "Shipment page renders the tracking number and delivered status",
        page.status == 200 and tracking_number in page.text and "Delivered" in page.text,
        f"HTTP {page.status}",
    )
    listing = http("GET", f"{stack.web}/shipments?status=DELIVERED")
    report.check(
        step, "Shipment list shows it", listing.status == 200 and tracking_number in listing.text
    )
    history = http("GET", f"{stack.web}/shipments/{shipment_id}/notifications")
    report.check(
        step,
        "Notification page shows the address",
        history.status == 200 and email in history.text,
    )

    metrics = http("GET", f"{stack.api}/metrics")
    report.check(
        "metrics",
        "API metrics expose webhook result counters",
        metrics.status == 200
        and 'parcelpulse_webhook_deliveries_total{result="DUPLICATE"}' in metrics.text,
    )


def _event_id(stack: Stack, delivery: dict[str, Any]) -> str:
    """The ParcelPulse tracking event id for a carrier event id."""
    return stack.receipts(delivery["event_id"])[0]["tracking_event_id"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"))
    parser.add_argument("--web-url", default=os.environ.get("WEB_URL", "http://localhost:3000"))
    parser.add_argument(
        "--simulator-url", default=os.environ.get("SIMULATOR_URL", "http://localhost:8100")
    )
    parser.add_argument("--mail-url", default=os.environ.get("MAIL_URL", "http://localhost:8025"))
    parser.add_argument("--json", metavar="PATH", help="Also write the results to this file")
    args = parser.parse_args()

    report = Report()
    started = time.monotonic()
    try:
        run(Stack(args), report)
    except Exception as error:
        report.check(
            "run", "Smoke test ran to completion", False, f"{type(error).__name__}: {error}"
        )

    failed = report.failed
    passed = len(report.checks) - len(failed)
    duration = round(time.monotonic() - started, 1)
    print(f"\n{passed}/{len(report.checks)} checks passed in {duration}s")
    for check in failed:
        print(f"  FAILED: [{check.step}] {check.name}  {check.detail}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "passed": passed,
                    "failed": len(failed),
                    "duration_seconds": duration,
                    "checks": [asdict(check) for check in report.checks],
                },
                handle,
                indent=2,
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
