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


def test_signing_secret_is_required_when_signatures_are_required() -> None:
    with pytest.raises(ValidationError, match="WEBHOOK_SIGNING_SECRET"):
        make_settings(webhook_signing_secret=None)


def test_short_signing_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="WEBHOOK_SIGNING_SECRET"):
        make_settings(webhook_signing_secret="too-short")


def test_signatures_can_be_disabled_for_local_development() -> None:
    settings = make_settings(webhook_signature_required=False, webhook_signing_secret=None)
    assert settings.webhook_signature_required is False


def test_production_requires_webhook_signatures() -> None:
    with pytest.raises(ValidationError, match="WEBHOOK_SIGNATURE_REQUIRED"):
        make_settings(environment="production", webhook_signature_required=False)


def test_signing_secret_is_not_exposed_in_repr() -> None:
    settings = make_settings(webhook_signing_secret="super-secret-value-0123456789")
    assert "super-secret-value" not in repr(settings)


def test_supported_carriers_are_parsed_from_a_comma_separated_string() -> None:
    settings = make_settings(supported_carriers="SimCarrier, othercarrier ,")
    assert settings.supported_carriers == ["simcarrier", "othercarrier"]
