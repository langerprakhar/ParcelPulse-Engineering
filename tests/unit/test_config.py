import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_defaults_disable_dev_endpoints() -> None:
    assert make_settings().enable_dev_endpoints is False


def test_production_rejects_dev_endpoints() -> None:
    with pytest.raises(ValidationError, match="ENABLE_DEV_ENDPOINTS"):
        make_settings(environment="production", enable_dev_endpoints=True)


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(environment="staging-ish")
