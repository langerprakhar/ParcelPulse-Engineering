# API specification

The authoritative contract is the OpenAPI document that FastAPI generates from
the code. This page explains how to get it and summarises the conventions that
apply to every endpoint.

## OpenAPI

With the service running:

| URL                    | Content                         |
| ---------------------- | ------------------------------- |
| `/openapi.json`        | OpenAPI 3.1 document            |
| `/docs`                | Swagger UI                      |
| `/redoc`               | ReDoc                           |

To export the document without starting a server or a database:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://unused:unused@localhost:1/unused"
$env:WEBHOOK_SIGNING_SECRET = "export-only-secret-0000"
python -c "import json; from parcelpulse_api.main import create_app; print(json.dumps(create_app().openapi(), indent=2))" > openapi.json
```

`tests/integration/test_operations.py` asserts that the public paths below are
present in the generated document.

## Endpoints

| Method | Path                                                | Purpose                                         |
| ------ | --------------------------------------------------- | ----------------------------------------------- |
| POST   | `/shipments`                                        | Register a shipment to track                    |
| GET    | `/shipments`                                        | List shipments, newest first (paginated)        |
| GET    | `/shipments/{shipment_id}`                          | Get a shipment                                  |
| GET    | `/shipments/by-tracking/{tracking_number}`          | Look up by tracking number                      |
| GET    | `/shipments/{shipment_id}/events`                   | Timeline, ordered by carrier event time         |
| GET    | `/shipments/{shipment_id}/notification-preferences` | Notification preferences (defaults until saved) |
| PUT    | `/shipments/{shipment_id}/notification-preferences` | Replace notification preferences                |
| GET    | `/shipments/{shipment_id}/notifications`            | Notification history, newest first              |
| GET    | `/carriers`                                         | Supported carrier codes                         |
| POST   | `/webhooks/carrier`                                 | Receive one carrier tracking event              |
| GET    | `/health`                                           | Liveness: the process is up                     |
| GET    | `/ready`                                            | Readiness: PostgreSQL and Redis answer          |
| GET    | `/metrics`                                          | Prometheus metrics (not in the OpenAPI document) |
| GET    | `/dev/webhook-receipts`                             | Development only, see below                     |

## Conventions

**Identifiers** are UUIDs. **Timestamps** are ISO 8601 with a UTC offset.

**Tracking numbers** are normalised before use: surrounding whitespace, inner
spaces and dashes are removed and letters are upper-cased. After
normalisation they must match `^[A-Z0-9]{6,40}$`. **Carrier codes** match
`^[a-z0-9][a-z0-9_-]{1,31}$` and must be listed in `SUPPORTED_CARRIERS`.

**Pagination** uses `limit` (1 to 100) and `offset`. List responses have the shape

```json
{ "items": [], "total": 0, "limit": 20, "offset": 0 }
```

**Errors** always use one envelope:

```json
{
  "error": { "code": "shipment_not_found", "message": "Shipment ... not found", "details": null },
  "correlation_id": "0b9f6c1e8e7a4b0fa2d4c6f5e3a1b2c3"
}
```

| Status | `code`                       | When                                                      |
| ------ | ---------------------------- | --------------------------------------------------------- |
| 401    | `invalid_webhook_signature`  | Webhook signature missing, stale or wrong                 |
| 404    | `shipment_not_found`         | No such shipment                                          |
| 404    | `not_found`                  | No such route                                             |
| 409    | `shipment_already_exists`    | `details.shipment_id` is the existing shipment            |
| 409    | `ambiguous_tracking_number`  | Tracking number exists for several carriers; pass `carrier` |
| 413    | `payload_too_large`          | Webhook body above `WEBHOOK_MAX_BODY_BYTES`               |
| 422    | `validation_error`           | `details` is a list of `{loc, message, type}`             |
| 422    | `unsupported_carrier`        | `details.supported_carriers` lists the accepted codes     |
| 422    | `event_time_in_future`       | Webhook `occurred_at` beyond the allowed clock skew       |
| 500    | `internal_error`             | Unexpected failure; details are only in the server log    |

Validation errors never echo the submitted values back.

**Correlation IDs.** Every response carries `X-Correlation-ID`. A caller may
supply its own in `X-Correlation-ID` or `X-Request-ID` (1 to 64 characters of
`A-Z a-z 0-9 . _ -`); otherwise one is generated. The same ID appears in every
log line for the request, is stored on the tracking event, the receipt and the
notification, and is passed to the worker.

## Carrier webhook contract

`POST /webhooks/carrier` with a JSON body:

```json
{
  "provider": "simcarrier",
  "event_id": "evt_6f1c0b7e2a9d4c53",
  "tracking_number": "SC4F7K2M9Q1X",
  "event_type": "OUT_FOR_DELIVERY",
  "occurred_at": "2026-09-30T07:45:00+00:00",
  "location": { "facility": "Bristol Delivery Office", "city": "Bristol", "region": "ENG", "country": "GB" },
  "description": "Loaded on delivery vehicle",
  "estimated_delivery_at": "2026-09-30T13:45:00+00:00"
}
```

| Field                   | Required | Notes                                                                 |
| ----------------------- | -------- | --------------------------------------------------------------------- |
| `provider`              | yes      | Carrier code                                                          |
| `event_id`              | yes      | 1 to 128 printable ASCII characters without spaces. The idempotency key |
| `tracking_number`       | yes      | Normalised as above                                                   |
| `event_type`            | yes      | `LABEL_CREATED`, `IN_TRANSIT`, `AT_DISTRIBUTION_CENTER`, `OUT_FOR_DELIVERY`, `DELIVERED`, `DELIVERY_EXCEPTION`, `RETURNED` |
| `occurred_at`           | yes      | Must include a UTC offset; at most one hour in the future             |
| `location`              | no       | Any of `facility`, `city`, `region`, `country`                        |
| `description`           | no       | Up to 500 characters                                                  |
| `estimated_delivery_at` | no       | Must include a UTC offset                                             |

Unknown fields are accepted and kept in the stored payload.

### Signature

```
X-Carrier-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>
```

The HMAC covers the timestamp and the exact bytes of the body. Requests whose
timestamp is more than `WEBHOOK_SIGNATURE_TOLERANCE_SECONDS` (default 300) away
from the server's clock are rejected, which bounds replay of a captured
request. Several `v1` values may be sent during a secret rotation; one match is
enough. Signatures can be switched off with `WEBHOOK_SIGNATURE_REQUIRED=false`
outside production only.

### Response

Every authenticated, valid delivery is answered with **200**, so that carriers
stop retrying:

```json
{
  "result": "PROCESSED",
  "duplicate": false,
  "receipt_id": "…",
  "shipment_id": "…",
  "tracking_event_id": "…",
  "shipment_status": "OUT_FOR_DELIVERY"
}
```

`result` is `PROCESSED`, `DUPLICATE`, `DUPLICATE_PAYLOAD_MISMATCH` or
`UNKNOWN_SHIPMENT`; see [webhook-idempotency.md](webhook-idempotency.md).

## Development namespace

`/dev/*` is mounted only when `ENABLE_DEV_ENDPOINTS=true`. The settings refuse
that flag together with `ENVIRONMENT=production`, and the router is not
registered in production at all. It currently holds one endpoint,
`GET /dev/webhook-receipts`, which lists every webhook delivery attempt and can
be filtered by `provider_event_id` or `tracking_number`.

## Authentication

Only the webhook endpoint is authenticated (by signature). The shipment and
notification endpoints have no authentication in v0.1: the API is meant to be
reachable only from the web application's server and trusted networks.
