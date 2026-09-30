# Carrier simulator

A stand-in for a parcel carrier. It plans a journey for each simulated shipment
and delivers the journey's tracking events to ParcelPulse as signed webhooks,
so the whole product can be developed and tested without a carrier account.

It can behave well (events in order) and badly, the way real carriers do:

| Behaviour            | How                                                                 |
| -------------------- | ------------------------------------------------------------------- |
| Normal sequence      | `advance` sends the next planned event                              |
| Duplicate delivery   | `duplicate` re-sends an event byte for byte with a fresh signature  |
| Delayed event        | `hold` withholds an event, `release-held` sends it later            |
| Out-of-order events  | `out-of-order` swaps the next two events; `lifecycle --shuffle`     |
| Delivery exception   | `exception` injects one; the `exception`/`returned` scenarios       |
| Retries              | failed deliveries are retried with exponential backoff              |
| Bursts               | `burst` plays out many complete journeys concurrently               |

The simulator implements the carrier's side of the webhook contract on its own
(`src/carrier_simulator/signing.py`); it shares no code with ParcelPulse.

## Event times

Each journey is scheduled to have *ended two hours before the shipment was
created in the simulator*, so every event carries a realistic past timestamp
no matter how quickly events are sent. `occurred_at` is therefore the planned
carrier time, never the time of sending, which is exactly what makes late and
swapped deliveries observable.

## Running

In the ParcelPulse stack the simulator runs as the `carrier-simulator` service
on <http://localhost:8100> (interactive API docs at `/docs`). To run it on its own:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env       # set WEBHOOK_SIGNING_SECRET to the API's secret
uvicorn carrier_simulator.app:create_app --factory --port 8100
```

State lives in memory and is lost on restart.

## Command line

```powershell
carrier-sim create --scenario standard --register --notification-email me@example.com
carrier-sim advance SC4F7K2M9Q1X --count 2
carrier-sim duplicate SC4F7K2M9Q1X
carrier-sim hold SC4F7K2M9Q1X
carrier-sim advance SC4F7K2M9Q1X
carrier-sim release-held SC4F7K2M9Q1X
carrier-sim lifecycle SC4F7K2M9Q1X --duplicates 1
carrier-sim burst --shipments 50 --shuffle --duplicates 1
```

`carrier-sim --help` lists every command. The simulator URL is taken from
`--url` or `SIMULATOR_URL` (default `http://localhost:8100`). Inside the stack:

```powershell
docker compose exec carrier-simulator carrier-sim list
```

`--register` also registers the shipment in ParcelPulse (`POST /shipments`), a
convenience for demos and tests. Without it, register the tracking number
yourself; events for an unregistered tracking number are acknowledged by
ParcelPulse with `UNKNOWN_SHIPMENT` and otherwise ignored.

## HTTP API

| Method and path                               | Purpose                                      |
| --------------------------------------------- | -------------------------------------------- |
| `GET /scenarios`                              | Available journeys                           |
| `POST /shipments`                             | Create a simulated shipment (sends nothing)  |
| `GET /shipments`, `GET /shipments/{tn}`       | Plans, event states and the delivery log     |
| `POST /shipments/{tn}/advance`                | Send the next planned event(s)               |
| `POST /shipments/{tn}/hold`                   | Withhold the next planned event(s)           |
| `POST /shipments/{tn}/release-held`           | Send held events late                        |
| `POST /shipments/{tn}/out-of-order`           | Send the next two events swapped             |
| `POST /shipments/{tn}/duplicate`              | Redeliver a sent event                       |
| `POST /shipments/{tn}/exception`              | Inject a delivery exception                  |
| `POST /shipments/{tn}/lifecycle`              | Send everything not yet sent                 |
| `POST /bursts`                                | Many complete journeys, concurrently         |
| `DELETE /shipments`                           | Forget all simulated shipments               |

Every sending operation returns the deliveries it made, each with its HTTP
attempts and the `result` ParcelPulse reported (`PROCESSED`, `DUPLICATE`, ...).

## Scenarios

| Name        | Journey                                                                          |
| ----------- | -------------------------------------------------------------------------------- |
| `standard`  | Label, transit, two depots, out for delivery, delivered                          |
| `exception` | As standard, but the first delivery attempt fails and a second attempt succeeds  |
| `returned`  | The address cannot be found and the parcel is returned to the sender             |

## Tests

```powershell
ruff check .
ruff format --check .
mypy
pytest
```

The tests replace ParcelPulse with a fake receiver behind a mock HTTP
transport; they need no network and no Docker.
