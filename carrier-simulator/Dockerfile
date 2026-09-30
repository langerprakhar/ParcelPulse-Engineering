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

RUN useradd --system --uid 10001 --no-create-home simulator
USER simulator

EXPOSE 8100

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "carrier_simulator.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
