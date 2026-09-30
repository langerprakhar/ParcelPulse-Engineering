"""Delivering one webhook, with the retries a real carrier would make."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2

from carrier_simulator.signing import SIGNATURE_HEADER, sign

logger = logging.getLogger("carrier_simulator.sender")


@dataclass(frozen=True, slots=True)
class Attempt:
    number: int
    # None when no HTTP response was received (connection error or timeout).
    status_code: int | None
    duration_ms: float
    error: str | None = None
    # The "result" field of the receiver's JSON response, when there is one.
    result: str | None = None


@dataclass(slots=True)
class SendResult:
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def delivered(self) -> bool:
        return bool(self.attempts) and _is_success(self.attempts[-1].status_code)

    @property
    def result(self) -> str | None:
        return self.attempts[-1].result if self.attempts else None


def _is_success(status_code: int | None) -> bool:
    return status_code is not None and 200 <= status_code < 300


def _should_retry(status_code: int | None) -> bool:
    # No response, a server error or "slow down": try again later.
    # Any other 4xx means the receiver rejected the request itself; repeating it cannot help.
    return status_code is None or status_code >= 500 or status_code == 429


class WebhookSender:
    def __init__(
        self,
        client: httpx2.Client,
        *,
        url: str,
        secret: str,
        max_attempts: int = 4,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._url = url
        self._secret = secret
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._clock = clock

    def send(self, body: bytes) -> SendResult:
        """POST ``body`` until it is accepted, rejected for good, or attempts run out.

        The body is sent byte-for-byte unchanged on every attempt; only the
        signature is recomputed, because it includes the current time.
        """
        outcome = SendResult()
        for number in range(1, self._max_attempts + 1):
            attempt = self._attempt(number, body)
            outcome.attempts.append(attempt)
            if not _should_retry(attempt.status_code):
                break
            if number < self._max_attempts:
                self._sleep(self._backoff_seconds * (2 ** (number - 1)))
        return outcome

    def _attempt(self, number: int, body: bytes) -> Attempt:
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: sign(self._secret, body, int(self._clock())),
        }
        started = time.perf_counter()
        try:
            response = self._client.post(self._url, content=body, headers=headers)
        except httpx2.HTTPError as exc:
            logger.warning("webhook attempt %d failed: %s", number, type(exc).__name__)
            return Attempt(
                number=number,
                status_code=None,
                duration_ms=_elapsed_ms(started),
                error=type(exc).__name__,
            )
        return Attempt(
            number=number,
            status_code=response.status_code,
            duration_ms=_elapsed_ms(started),
            result=_result_of(response),
        )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def _result_of(response: httpx2.Response) -> str | None:
    try:
        payload: Any = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        if isinstance(payload.get("result"), str):
            return str(payload["result"])
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return str(error["code"])
    return None
