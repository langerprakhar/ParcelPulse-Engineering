from datetime import timedelta

import pytest

from parcelpulse_worker.retry import backoff_delay


@pytest.mark.parametrize(
    ("attempt", "expected_seconds"),
    [(1, 30), (2, 60), (3, 120), (4, 240), (5, 480)],
)
def test_delay_doubles_with_each_attempt(attempt: int, expected_seconds: int) -> None:
    delay = backoff_delay(attempt, base_seconds=30, max_seconds=3600)
    assert delay == timedelta(seconds=expected_seconds)


def test_delay_is_capped() -> None:
    assert backoff_delay(8, base_seconds=30, max_seconds=3600) == timedelta(seconds=3600)
    assert backoff_delay(10_000, base_seconds=30, max_seconds=3600) == timedelta(seconds=3600)


@pytest.mark.parametrize("attempt", [0, -1])
def test_attempt_numbers_start_at_one(attempt: int) -> None:
    with pytest.raises(ValueError):
        backoff_delay(attempt, base_seconds=30, max_seconds=3600)
