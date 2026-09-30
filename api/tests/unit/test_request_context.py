import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from parcelpulse_api.correlation import CORRELATION_HEADER, set_correlation_id
from parcelpulse_api.logging_config import REDACTED, JsonFormatter


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "parcelpulse-api"


def test_response_carries_generated_correlation_id(client: TestClient) -> None:
    response = client.get("/health")
    assert len(response.headers[CORRELATION_HEADER]) == 32


def test_caller_supplied_correlation_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={CORRELATION_HEADER: "carrier-retry-42"})
    assert response.headers[CORRELATION_HEADER] == "carrier-retry-42"


def test_unsafe_correlation_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={CORRELATION_HEADER: "bad id\twith spaces"})
    assert response.headers[CORRELATION_HEADER] != "bad id\twith spaces"
    assert len(response.headers[CORRELATION_HEADER]) == 32


def test_unknown_route_returns_structured_error(client: TestClient) -> None:
    response = client.get("/does-not-exist", headers={CORRELATION_HEADER: "abc123"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None},
        "correlation_id": "abc123",
    }


def test_unhandled_exception_becomes_structured_500(app: FastAPI) -> None:
    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert body["correlation_id"] == response.headers[CORRELATION_HEADER]


def test_json_formatter_includes_correlation_id_and_redacts_secrets() -> None:
    set_correlation_id("corr-1")
    record = logging.LogRecord("parcelpulse.test", logging.INFO, __file__, 1, "hello", (), None)
    record.shipment_id = "abc"
    record.webhook_signature = "t=1,v1=deadbeef"

    entry = json.loads(JsonFormatter("parcelpulse-api").format(record))

    assert entry["message"] == "hello"
    assert entry["correlation_id"] == "corr-1"
    assert entry["shipment_id"] == "abc"
    assert entry["webhook_signature"] == REDACTED
    set_correlation_id(None)
