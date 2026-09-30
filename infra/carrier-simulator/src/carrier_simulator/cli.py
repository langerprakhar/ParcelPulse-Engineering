"""Command-line client for a running carrier simulator.

    carrier-sim create --scenario standard --register
    carrier-sim advance SC4F7K2M9Q1X --count 2
    carrier-sim duplicate SC4F7K2M9Q1X
    carrier-sim hold SC4F7K2M9Q1X
    carrier-sim release-held SC4F7K2M9Q1X
    carrier-sim lifecycle SC4F7K2M9Q1X --shuffle --duplicates 1

The simulator URL comes from --url or the SIMULATOR_URL environment variable
(default http://localhost:8100). Responses are printed as JSON.
"""

import argparse
import json
import os
import sys
from typing import Any

import httpx2

DEFAULT_URL = "http://localhost:8100"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carrier-sim", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--url",
        default=os.environ.get("SIMULATOR_URL", DEFAULT_URL),
        help="Base URL of the simulator (default: %(default)s)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("scenarios", help="List the available journeys")
    commands.add_parser("list", help="List simulated shipments")
    commands.add_parser("reset", help="Forget every simulated shipment")

    create = commands.add_parser("create", help="Create a simulated shipment")
    create.add_argument("--scenario", default="standard")
    create.add_argument("--tracking-number")
    create.add_argument(
        "--register", action="store_true", help="Also register the shipment in ParcelPulse"
    )
    create.add_argument("--notification-email")

    def with_tracking_number(name: str, help_text: str) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("tracking_number")
        return command

    with_tracking_number("show", "Show a shipment's plan and delivery log")

    advance = with_tracking_number("advance", "Send the next planned event(s)")
    advance.add_argument("--count", type=int, default=1)

    hold = with_tracking_number("hold", "Withhold the next planned event(s)")
    hold.add_argument("--count", type=int, default=1)

    with_tracking_number("release-held", "Send held events late (delayed events)")
    with_tracking_number("out-of-order", "Send the next two events in swapped order")
    with_tracking_number("exception", "Inject a delivery exception")

    duplicate = with_tracking_number("duplicate", "Redeliver an already sent event")
    duplicate.add_argument("--event-id", help="Defaults to the last event sent")
    duplicate.add_argument("--count", type=int, default=1)

    lifecycle = with_tracking_number("lifecycle", "Send every event not yet sent")
    lifecycle.add_argument("--shuffle", action="store_true")
    lifecycle.add_argument("--duplicates", type=int, default=0)

    burst = commands.add_parser("burst", help="Play out many complete journeys concurrently")
    burst.add_argument("--shipments", type=int, default=10)
    burst.add_argument("--scenario", default="standard")
    burst.add_argument("--no-register", action="store_true")
    burst.add_argument("--shuffle", action="store_true")
    burst.add_argument("--duplicates", type=int, default=0)
    burst.add_argument("--concurrency", type=int, default=8)

    return parser


def build_request(args: argparse.Namespace) -> tuple[str, str, dict[str, Any] | None]:
    """Translate parsed arguments into (method, path, JSON body)."""
    command = args.command
    if command == "scenarios":
        return "GET", "/scenarios", None
    if command == "list":
        return "GET", "/shipments", None
    if command == "reset":
        return "DELETE", "/shipments", None
    if command == "create":
        body: dict[str, Any] = {"scenario": args.scenario, "register": args.register}
        if args.tracking_number:
            body["tracking_number"] = args.tracking_number
        if args.notification_email:
            body["notification_email"] = args.notification_email
        return "POST", "/shipments", body
    if command == "burst":
        return (
            "POST",
            "/bursts",
            {
                "shipments": args.shipments,
                "scenario": args.scenario,
                "register": not args.no_register,
                "shuffle": args.shuffle,
                "duplicates": args.duplicates,
                "concurrency": args.concurrency,
            },
        )

    base = f"/shipments/{args.tracking_number}"
    if command == "show":
        return "GET", base, None
    if command in ("advance", "hold"):
        return "POST", f"{base}/{command}", {"count": args.count}
    if command == "duplicate":
        duplicate_body: dict[str, Any] = {"count": args.count}
        if args.event_id:
            duplicate_body["event_id"] = args.event_id
        return "POST", f"{base}/duplicate", duplicate_body
    if command == "lifecycle":
        return (
            "POST",
            f"{base}/lifecycle",
            {"shuffle": args.shuffle, "duplicates": args.duplicates},
        )
    # release-held, out-of-order, exception
    return "POST", f"{base}/{command}", None


def main(argv: list[str] | None = None, client: httpx2.Client | None = None) -> int:
    args = build_parser().parse_args(argv)
    method, path, body = build_request(args)
    owns_client = client is None
    client = client or httpx2.Client(base_url=args.url, timeout=120)
    try:
        response = client.request(method, path, json=body)
    except httpx2.HTTPError as exc:
        print(f"could not reach the simulator at {args.url}: {exc}", file=sys.stderr)
        return 2
    finally:
        if owns_client:
            client.close()

    try:
        print(json.dumps(response.json(), indent=2))
    except ValueError:
        print(response.text)
    return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
