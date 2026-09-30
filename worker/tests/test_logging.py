import json
import logging

from parcelpulse_worker.logging_config import (
    REDACTED,
    JsonFormatter,
    correlation_scope,
    get_correlation_id,
)


def make_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord("parcelpulse.test", logging.INFO, __file__, 1, "hello", (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_includes_correlation_id_and_extras() -> None:
    with correlation_scope("corr-1"):
        entry = json.loads(
            JsonFormatter("parcelpulse-worker").format(make_record(notification_id="abc"))
        )

    assert entry["message"] == "hello"
    assert entry["service"] == "parcelpulse-worker"
    assert entry["correlation_id"] == "corr-1"
    assert entry["notification_id"] == "abc"


def test_sensitive_extras_are_redacted() -> None:
    entry = json.loads(
        JsonFormatter("parcelpulse-worker").format(make_record(smtp_password="hunter2"))
    )
    assert entry["smtp_password"] == REDACTED


def test_correlation_scope_is_restored_on_exit() -> None:
    with correlation_scope("outer"):
        with correlation_scope("inner"):
            assert get_correlation_id() == "inner"
        assert get_correlation_id() == "outer"
    assert get_correlation_id() is None
