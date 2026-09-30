"""The simulator's HTTP API and command-line client."""

import json
from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient

from carrier_simulator import cli
from carrier_simulator.app import create_app
from tests.conftest import FakeParcelPulse, make_settings


@pytest.fixture
def client(http_client: httpx2.Client) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(), client=http_client)) as test_client:
        yield test_client


def create(client: TestClient, **body: object) -> dict:
    response = client.post("/shipments", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_scenarios_are_listed(client: TestClient) -> None:
    scenarios = client.get("/scenarios").json()
    assert set(scenarios) == {"standard", "exception", "returned"}
    assert scenarios["standard"][-1]["event_type"] == "DELIVERED"


def test_create_returns_the_planned_journey(client: TestClient) -> None:
    shipment = create(client, scenario="standard", tracking_number="SC4F7K2M9Q1X")

    assert shipment["tracking_number"] == "SC4F7K2M9Q1X"
    assert shipment["registered"] is False
    assert [event["state"] for event in shipment["events"]] == ["planned"] * 7
    assert shipment["deliveries"] == []


def test_create_with_registration(client: TestClient, receiver: FakeParcelPulse) -> None:
    shipment = create(client, register=True, notification_email="dev@example.com")

    assert shipment["registered"] is True
    assert receiver.registrations[0]["notification_email"] == "dev@example.com"


def test_registration_failure_is_reported_as_bad_gateway(
    client: TestClient, receiver: FakeParcelPulse
) -> None:
    receiver.registration_status = 500

    response = client.post("/shipments", json={"register": True})

    assert response.status_code == 502
    assert "HTTP 500" in response.json()["error"]


def test_existing_registration_is_accepted(client: TestClient, receiver: FakeParcelPulse) -> None:
    receiver.registration_status = 409
    assert create(client, register=True)["registered"] is True


def test_advance_duplicate_and_inspect(client: TestClient) -> None:
    tracking_number = create(client)["tracking_number"]

    advanced = client.post(f"/shipments/{tracking_number}/advance", json={"count": 2}).json()
    duplicated = client.post(f"/shipments/{tracking_number}/duplicate").json()
    shipment = client.get(f"/shipments/{tracking_number}").json()

    assert [d["event_type"] for d in advanced["deliveries"]] == ["LABEL_CREATED", "IN_TRANSIT"]
    assert [d["result"] for d in advanced["deliveries"]] == ["PROCESSED", "PROCESSED"]
    (repeat,) = duplicated["deliveries"]
    assert (repeat["duplicate"], repeat["result"]) == (True, "DUPLICATE")
    assert repeat["attempts"][0]["status_code"] == 200
    assert len(shipment["deliveries"]) == 3
    assert [event["state"] for event in shipment["events"]][:3] == ["sent", "sent", "planned"]


def test_hold_and_release(client: TestClient, receiver: FakeParcelPulse) -> None:
    tracking_number = create(client)["tracking_number"]

    held = client.post(f"/shipments/{tracking_number}/hold").json()
    client.post(f"/shipments/{tracking_number}/advance")
    released = client.post(f"/shipments/{tracking_number}/release-held").json()

    assert held["held"][0]["event_type"] == "LABEL_CREATED"
    assert released["deliveries"][0]["event_type"] == "LABEL_CREATED"
    assert receiver.event_types == ["IN_TRANSIT", "LABEL_CREATED"]


def test_out_of_order_exception_and_lifecycle(
    client: TestClient, receiver: FakeParcelPulse
) -> None:
    tracking_number = create(client)["tracking_number"]

    client.post(f"/shipments/{tracking_number}/out-of-order")
    client.post(f"/shipments/{tracking_number}/exception")
    lifecycle = client.post(
        f"/shipments/{tracking_number}/lifecycle", json={"duplicates": 1}
    ).json()

    assert receiver.event_types[:3] == ["IN_TRANSIT", "LABEL_CREATED", "DELIVERY_EXCEPTION"]
    assert len(lifecycle["deliveries"]) == 10
    assert receiver.event_types[-1] == "DELIVERED"


def test_unknown_shipment_is_404_and_invalid_operation_is_409(client: TestClient) -> None:
    assert client.post("/shipments/SCNOBODY0001/advance").status_code == 404

    tracking_number = create(client)["tracking_number"]
    conflict = client.post(f"/shipments/{tracking_number}/release-held")
    assert conflict.status_code == 409
    assert "no held events" in conflict.json()["error"]


def test_invalid_input_is_rejected(client: TestClient) -> None:
    assert client.post("/shipments", json={"tracking_number": "no spaces!"}).status_code == 422
    assert client.post("/shipments", json={"scenario": "teleport"}).status_code == 409
    assert client.post("/bursts", json={"shipments": 0}).status_code == 422


def test_burst_and_reset(client: TestClient) -> None:
    summary = client.post("/bursts", json={"shipments": 5, "duplicates": 1}).json()

    assert summary["shipments"] == 5
    assert summary["undelivered"] == 0
    assert summary["results"] == {"PROCESSED": 35, "DUPLICATE": 35}
    assert len(client.get("/shipments").json()) == 5

    assert client.delete("/shipments").json() == {"removed": 5}
    assert client.get("/shipments").json() == []


# --- Command-line client ------------------------------------------------------


def run_cli(client: TestClient, capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict]:
    exit_code = cli.main(list(argv), client=client)
    return exit_code, json.loads(capsys.readouterr().out)


def test_cli_drives_a_shipment_through_its_journey(
    client: TestClient, receiver: FakeParcelPulse, capsys: pytest.CaptureFixture[str]
) -> None:
    code, created = run_cli(client, capsys, "create", "--tracking-number", "SC4F7K2M9Q1X")
    assert code == 0
    assert created["tracking_number"] == "SC4F7K2M9Q1X"

    code, advanced = run_cli(client, capsys, "advance", "SC4F7K2M9Q1X", "--count", "2")
    assert code == 0
    assert len(advanced["deliveries"]) == 2

    code, duplicated = run_cli(client, capsys, "duplicate", "SC4F7K2M9Q1X")
    assert duplicated["deliveries"][0]["result"] == "DUPLICATE"

    run_cli(client, capsys, "hold", "SC4F7K2M9Q1X")
    run_cli(client, capsys, "advance", "SC4F7K2M9Q1X")
    code, released = run_cli(client, capsys, "release-held", "SC4F7K2M9Q1X")
    assert released["deliveries"][0]["event_type"] == "AT_DISTRIBUTION_CENTER"

    code, _ = run_cli(client, capsys, "lifecycle", "SC4F7K2M9Q1X", "--duplicates", "1")
    assert code == 0
    assert receiver.event_types[-1] == "DELIVERED"

    code, shown = run_cli(client, capsys, "show", "SC4F7K2M9Q1X")
    assert all(event["state"] == "sent" for event in shown["events"])


def test_cli_reports_failures_through_its_exit_code(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    code, body = run_cli(client, capsys, "advance", "SCNOBODY0001")
    assert code == 1
    assert "no simulated shipment" in body["error"]


def test_cli_burst_and_listing(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    code, summary = run_cli(client, capsys, "burst", "--shipments", "3", "--shuffle")
    assert (code, summary["shipments"], summary["undelivered"]) == (0, 3, 0)

    code = cli.main(["list"], client=client)
    assert len(json.loads(capsys.readouterr().out)) == 3

    code, removed = run_cli(client, capsys, "reset")
    assert removed == {"removed": 3}
