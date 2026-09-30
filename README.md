# parcelpulse-worker

Asynchronous notification worker for ParcelPulse, a package tracking and
delivery notification platform.

The API (`parcelpulse-api`) records which notifications are owed. This service
delivers them.

## Requirements

- Python 3.12

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Checks

```powershell
ruff check .
ruff format --check .
mypy
pytest
```
