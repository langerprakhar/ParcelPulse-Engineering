"""Static checks on docker-compose.yml.

Needs the Docker CLI (for ``docker compose config``) but starts nothing::

    python -m pytest tests/test_compose.py
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

EXPECTED_SERVICES = {
    "postgres",
    "redis",
    "mailpit",
    "api-migrate",
    "api",
    "worker",
    "worker-sweeper",
    "carrier-simulator",
    "web",
}
# Windows hands out ports from 49152 upwards dynamically; publishing there can fail.
FIRST_DYNAMIC_PORT = 49152


def _referenced_variables() -> set[str]:
    return set(re.findall(r"\$\{([A-Z_]+)", COMPOSE_FILE.read_text(encoding="utf-8")))


def _compose_config() -> tuple[dict[str, Any], str]:
    # Resolve with the file's own defaults only: ignore a developer's .env and any
    # of the variables set in the surrounding shell.
    referenced = _referenced_variables()
    environment = {key: value for key, value in os.environ.items() if key not in referenced}
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-f",
            str(COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=environment,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout), completed.stderr


@pytest.fixture(scope="module")
def resolved() -> tuple[dict[str, Any], str]:
    return _compose_config()


@pytest.fixture(scope="module")
def services(resolved: tuple[dict[str, Any], str]) -> dict[str, Any]:
    return resolved[0]["services"]


def test_config_is_valid_and_needs_no_env_file(resolved: tuple[dict[str, Any], str]) -> None:
    _, warnings = resolved
    assert "variable is not set" not in warnings, warnings


def test_stack_defines_every_expected_service(services: dict[str, Any]) -> None:
    assert set(services) == EXPECTED_SERVICES


def test_third_party_images_are_pinned_to_a_version(services: dict[str, Any]) -> None:
    for name in ("postgres", "redis", "mailpit"):
        image = services[name]["image"]
        tag = image.rsplit(":", 1)[1] if ":" in image else ""
        assert re.search(r"\d+\.\d+", tag), f"{name} uses an unpinned image: {image}"
        assert tag != "latest"


def test_application_services_are_built_from_the_component_directories(
    services: dict[str, Any],
) -> None:
    contexts = {
        name: Path(services[name]["build"]["context"]).name
        for name in ("api-migrate", "api", "worker", "worker-sweeper", "web", "carrier-simulator")
    }
    assert contexts == {
        "api-migrate": "api",
        "api": "api",
        "worker": "worker",
        "worker-sweeper": "worker",
        "web": "web",
        "carrier-simulator": "carrier-simulator",
    }


@pytest.mark.parametrize("name", ["postgres", "redis", "mailpit", "api"])
def test_service_declares_a_healthcheck(services: dict[str, Any], name: str) -> None:
    assert services[name].get("healthcheck", {}).get("test"), f"{name} has no healthcheck"


def test_api_health_means_ready_not_merely_alive(services: dict[str, Any]) -> None:
    assert "/ready" in " ".join(services["api"]["healthcheck"]["test"])


@pytest.mark.parametrize(
    ("service", "dependency", "condition"),
    [
        ("api-migrate", "postgres", "service_healthy"),
        ("api", "api-migrate", "service_completed_successfully"),
        ("api", "redis", "service_healthy"),
        ("worker", "api-migrate", "service_completed_successfully"),
        ("worker", "redis", "service_healthy"),
        ("worker", "mailpit", "service_healthy"),
        ("worker-sweeper", "api-migrate", "service_completed_successfully"),
        ("carrier-simulator", "api", "service_healthy"),
        ("web", "api", "service_healthy"),
    ],
)
def test_startup_order(
    services: dict[str, Any], service: str, dependency: str, condition: str
) -> None:
    assert services[service]["depends_on"][dependency]["condition"] == condition


def test_migration_job_runs_once(services: dict[str, Any]) -> None:
    migrate = services["api-migrate"]
    assert migrate["command"] == ["alembic", "upgrade", "head"]
    assert migrate.get("restart") == "no"


def test_published_ports_are_unique_and_outside_the_dynamic_range(
    services: dict[str, Any],
) -> None:
    published = [
        int(port["published"]) for service in services.values() for port in service.get("ports", [])
    ]
    assert len(published) == len(set(published)), f"duplicate host ports: {published}"
    assert all(port < FIRST_DYNAMIC_PORT for port in published), published


def test_api_and_carrier_simulator_share_the_webhook_secret(services: dict[str, Any]) -> None:
    api_secret = services["api"]["environment"]["WEBHOOK_SIGNING_SECRET"]
    simulator_secret = services["carrier-simulator"]["environment"]["WEBHOOK_SIGNING_SECRET"]
    assert api_secret == simulator_secret
    assert len(api_secret) >= 16


def test_worker_and_sweeper_are_configured_identically(services: dict[str, Any]) -> None:
    assert services["worker"]["environment"] == services["worker-sweeper"]["environment"]


def test_services_talk_to_each_other_over_the_compose_network(services: dict[str, Any]) -> None:
    assert "@postgres:5432/" in services["api"]["environment"]["DATABASE_URL"]
    assert services["api"]["environment"]["REDIS_URL"] == "redis://redis:6379/0"
    assert services["worker"]["environment"]["SMTP_HOST"] == "mailpit"
    assert services["web"]["environment"]["API_BASE_URL"] == "http://api:8000"
    assert (
        services["carrier-simulator"]["environment"]["WEBHOOK_URL"]
        == "http://api:8000/webhooks/carrier"
    )


def test_env_example_documents_exactly_the_variables_compose_reads() -> None:
    referenced = _referenced_variables()
    documented = {
        line.split("=", 1)[0]
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    assert documented == referenced
