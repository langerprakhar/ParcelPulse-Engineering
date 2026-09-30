"""Retry schedule for failed notification attempts."""

from datetime import timedelta


def backoff_delay(attempt: int, *, base_seconds: float, max_seconds: float) -> timedelta:
    """How long to wait after attempt number ``attempt`` (1-based) has failed.

    Exponential: base, 2x base, 4x base, ... capped at ``max_seconds``. There is
    deliberately no jitter: volumes are low and a predictable schedule is easier
    to reason about and to test.
    """
    if attempt < 1:
        raise ValueError("attempt must be 1 or greater")
    # Cap the exponent as well as the result, so huge attempt counts cannot overflow.
    seconds = min(max_seconds, base_seconds * (2 ** min(attempt - 1, 32)))
    return timedelta(seconds=seconds)
