FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# constraints.txt pins every transitive dependency (see scripts/update-constraints.ps1).
COPY pyproject.toml README.md constraints.txt ./
COPY src ./src
RUN pip install --constraint constraints.txt .

RUN useradd --system --uid 10001 --no-create-home parcelpulse
USER parcelpulse

# No HTTP port: health means "PostgreSQL and Redis are reachable from here".
HEALTHCHECK --interval=15s --timeout=10s --start-period=10s --retries=4 \
    CMD ["python", "-m", "parcelpulse_worker.healthcheck"]

# The same image runs the sweeper with: python -m parcelpulse_worker.sweeper
CMD ["dramatiq", "parcelpulse_worker.actors", "--processes", "1", "--threads", "4"]
