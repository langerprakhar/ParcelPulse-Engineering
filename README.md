# parcelpulse-api

HTTP API for ParcelPulse, a package tracking and delivery notification platform.

This service owns shipment data, ingests carrier webhook events and exposes the
shipment timeline to the web dashboard.

## Requirements

- Python 3.12
- PostgreSQL 17 (a disposable one is provided through Docker for tests)

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Database

The schema is managed with Alembic. `DATABASE_URL` selects the database.

```powershell
alembic upgrade head      # create or update the schema
alembic downgrade -1      # undo the latest revision
```

## Run

```powershell
uvicorn parcelpulse_api.main:create_app --factory --reload --port 8000
```

- Liveness: `GET http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`

## Tests

Unit tests need nothing but Python. Integration tests need PostgreSQL; they
rebuild the schema from zero with Alembic at the start of every run and empty
all tables before each test.

```powershell
docker compose -f docker-compose.dev.yml up -d --wait   # PostgreSQL on localhost:25432
pytest tests/unit
pytest tests/integration
docker compose -f docker-compose.dev.yml down
```

Set `TEST_DATABASE_URL` to use a different database. Its name must end in
`_test`, because the test run drops and recreates the `public` schema.

## Checks

```powershell
ruff check .
ruff format --check .
mypy
```
