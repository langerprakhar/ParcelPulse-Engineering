"""SmtpEmailSender against a real SMTP server running in-process (aiosmtpd)."""

import socket
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import pytest
from aiosmtpd.controller import Controller

from parcelpulse_worker.senders import (
    PermanentDeliveryError,
    SmtpEmailSender,
    TransientDeliveryError,
)


class RecordingHandler:
    """Accepts mail, except for recipients the test has told it to refuse."""

    def __init__(self) -> None:
        self.received: list[Any] = []
        self.recipient_response: str | None = None
        self.data_response: str | None = None

    async def handle_RCPT(
        self, server: Any, session: Any, envelope: Any, address: str, rcpt_options: Any
    ) -> str:
        if self.recipient_response is not None:
            return self.recipient_response
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:
        if self.data_response is not None:
            return self.data_response
        self.received.append(envelope)
        return "250 Message accepted for delivery"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def handler() -> RecordingHandler:
    return RecordingHandler()


@pytest.fixture
def smtp_port(handler: RecordingHandler) -> Iterator[int]:
    port = free_port()
    controller = Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    yield port
    controller.stop()


def make_message() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "ParcelPulse <notifications@parcelpulse.local>"
    message["To"] = "recipient@example.com"
    message["Subject"] = "Delivered: SC4F7K2M9Q1X"
    message["Message-ID"] = "<abc@notifications.parcelpulse>"
    message.set_content("Your parcel SC4F7K2M9Q1X has been delivered.\n")
    return message


def test_message_is_delivered_over_smtp(handler: RecordingHandler, smtp_port: int) -> None:
    SmtpEmailSender(host="127.0.0.1", port=smtp_port, timeout=5).send(make_message())

    (envelope,) = handler.received
    assert envelope.mail_from == "notifications@parcelpulse.local"
    assert envelope.rcpt_tos == ["recipient@example.com"]
    content = envelope.content.decode()
    assert "Subject: Delivered: SC4F7K2M9Q1X" in content
    assert "Message-ID: <abc@notifications.parcelpulse>" in content
    assert "Your parcel SC4F7K2M9Q1X has been delivered." in content


def test_recipient_refused_with_5xx_is_permanent(handler: RecordingHandler, smtp_port: int) -> None:
    handler.recipient_response = "550 No such user here"

    with pytest.raises(PermanentDeliveryError, match="550"):
        SmtpEmailSender(host="127.0.0.1", port=smtp_port, timeout=5).send(make_message())
    assert handler.received == []


def test_recipient_deferred_with_4xx_is_transient(
    handler: RecordingHandler, smtp_port: int
) -> None:
    handler.recipient_response = "450 Mailbox busy, try again later"

    with pytest.raises(TransientDeliveryError, match="450"):
        SmtpEmailSender(host="127.0.0.1", port=smtp_port, timeout=5).send(make_message())


def test_message_rejected_with_5xx_is_permanent(handler: RecordingHandler, smtp_port: int) -> None:
    handler.data_response = "554 Message rejected as spam"

    with pytest.raises(PermanentDeliveryError, match="554"):
        SmtpEmailSender(host="127.0.0.1", port=smtp_port, timeout=5).send(make_message())


def test_message_deferred_with_4xx_is_transient(handler: RecordingHandler, smtp_port: int) -> None:
    handler.data_response = "451 Temporary local problem"

    with pytest.raises(TransientDeliveryError, match="451"):
        SmtpEmailSender(host="127.0.0.1", port=smtp_port, timeout=5).send(make_message())


def test_unreachable_server_is_transient() -> None:
    sender = SmtpEmailSender(host="127.0.0.1", port=free_port(), timeout=2)

    with pytest.raises(TransientDeliveryError):
        sender.send(make_message())
