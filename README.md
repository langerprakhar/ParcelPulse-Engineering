# parcelpulse-api

HTTP API for ParcelPulse, a package tracking and delivery notification platform.

This service owns shipment data, ingests carrier webhook events and exposes the
shipment timeline to the web dashboard.

## Requirements

- Python 3.12

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Run

```powershell
uvicorn parcelpulse_api.main:create_app --factory --reload --port 8000
```

- Liveness: `GET http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`

## Checks

```powershell
ruff check .
ruff format --check .
mypy
pytest
```
