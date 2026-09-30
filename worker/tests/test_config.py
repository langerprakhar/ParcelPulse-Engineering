import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_defaults_describe_a_local_development_setup() -> None:
    settings = make_settings()
    assert settings.notification_queue_name == "notifications"
    assert settings.notification_actor_name == "deliver_notification"
    assert settings.email_provider == "smtp"
    assert (settings.smtp_host, settings.smtp_port) == ("localhost", 1025)
    assert settings.notification_max_attempts == 5


def test_database_url_is_required() -> None:
    with pytest.raises(ValidationError):
        make_settings(database_url=None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"notification_max_attempts": 0},
        {"notification_retry_base_seconds": 0},
        {"sending_lease_seconds": -1},
        {"sweep_batch_size": 0},
        {"email_provider": "carrier-pigeon"},
    ],
)
def test_nonsensical_values_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_settings(**overrides)


def test_smtp_password_is_not_exposed_in_repr() -> None:
    settings = make_settings(smtp_password="super-secret-smtp-password")
    assert "super-secret-smtp-password" not in repr(settings)
