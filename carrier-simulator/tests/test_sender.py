"""Webhook delivery: signing and carrier-style retries."""

import httpx2
import pytest

from carrier_simulator.sender import WebhookSender
from tests.conftest import SECRET, WEBHOOK_URL, FakeParcelPulse, signature_is_valid

BODY = b'{"event_id":"evt_1","event_type":"IN_TRANSIT"}'


def test_accepted_delivery_takes_one_signed_attempt(
    sender: WebhookSender, receiver: FakeParcelPulse, sleeps: list[float]
) -> None:
    outcome = sender.send(BODY)

    assert outcome.delivered is True
    assert outcome.result == "PROCESSED"
    assert [(attempt.number, attempt.status_code) for attempt in outcome.attempts] == [(1, 200)]
    assert sleeps == []
    (webhook,) = receiver.webhooks
    assert webhook.body == BODY
    assert signature_is_valid(webhook.signature, BODY)


def test_server_error_is_retried_until_accepted(
    sender: WebhookSender, receiver: FakeParcelPulse, sleeps: list[float]
) -> None:
    receiver.scripted = [500, 503]

    outcome = sender.send(BODY)

    assert outcome.delivered is True
    assert [attempt.status_code for attempt in outcome.attempts] == [500, 503, 200]
    assert sleeps == [0.5, 1.0]


def test_connection_failure_is_retried(
    sender: WebhookSender, receiver: FakeParcelPulse, sleeps: list[float]
) -> None:
    receiver.scripted = [httpx2.ConnectError("connection refused")]

    outcome = sender.send(BODY)

    assert outcome.delivered is True
    first, second = outcome.attempts
    assert (first.status_code, first.error) == (None, "ConnectError")
    assert second.status_code == 200
    assert sleeps == [0.5]


def test_rate_limiting_is_retried(sender: WebhookSender, receiver: FakeParcelPulse) -> None:
    receiver.scripted = [429]

    outcome = sender.send(BODY)

    assert [attempt.status_code for attempt in outcome.attempts] == [429, 200]


def test_delivery_is_abandoned_after_the_maximum_number_of_attempts(
    sender: WebhookSender, receiver: FakeParcelPulse, sleeps: list[float]
) -> None:
    receiver.scripted = [500, 500, 500, 500, 500]

    outcome = sender.send(BODY)

    assert outcome.delivered is False
    assert len(outcome.attempts) == 4
    # Exponential backoff between attempts, none after the last.
    assert sleeps == [0.5, 1.0, 2.0]
    assert len(receiver.webhooks) == 4


@pytest.mark.parametrize("status_code", [400, 401, 413, 422])
def test_rejection_by_the_receiver_is_not_retried(
    sender: WebhookSender, receiver: FakeParcelPulse, sleeps: list[float], status_code: int
) -> None:
    receiver.scripted = [status_code]

    outcome = sender.send(BODY)

    assert outcome.delivered is False
    assert [attempt.status_code for attempt in outcome.attempts] == [status_code]
    assert outcome.result == f"http_{status_code}"
    assert sleeps == []


def test_retries_resend_the_same_bytes_with_a_fresh_signature(
    http_client: httpx2.Client, receiver: FakeParcelPulse
) -> None:
    ticks = iter([1_790_000_000, 1_790_000_030])
    sender = WebhookSender(
        http_client,
        url=WEBHOOK_URL,
        secret=SECRET,
        sleep=lambda _: None,
        clock=lambda: next(ticks),
    )
    receiver.scripted = [500]

    sender.send(BODY)

    first, second = receiver.webhooks
    assert first.body == second.body == BODY
    assert first.signature.startswith("t=1790000000,")
    assert second.signature.startswith("t=1790000030,")
    assert signature_is_valid(first.signature, BODY)
    assert signature_is_valid(second.signature, BODY)


def test_wrong_secret_is_rejected_by_the_receiver(
    http_client: httpx2.Client, receiver: FakeParcelPulse
) -> None:
    sender = WebhookSender(http_client, url=WEBHOOK_URL, secret="a-different-secret-000000")

    outcome = sender.send(BODY)

    assert outcome.delivered is False
    assert outcome.result == "invalid_webhook_signature"
