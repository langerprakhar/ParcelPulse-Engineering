"""Email transports.

A sender either delivers the message, raises :class:`PermanentDeliveryError`
(retrying cannot help, e.g. the recipient address was refused) or raises
anything else, which the caller treats as transient and retries.
"""

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("parcelpulse.worker.senders")


class DeliveryError(Exception):
    """A message could not be delivered."""


class TransientDeliveryError(DeliveryError):
    """Worth retrying: the mail server was unreachable, busy or misconfigured."""


class PermanentDeliveryError(DeliveryError):
    """Not worth retrying: this particular message will never be accepted."""


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


def _is_permanent(code: int) -> bool:
    return 500 <= code < 600


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        starttls: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._starttls = starttls
        self._timeout = timeout

    def send(self, message: EmailMessage) -> None:
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._starttls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password or "")
                smtp.send_message(message)
        except smtplib.SMTPRecipientsRefused as exc:
            codes = [code for code, _ in exc.recipients.values()]
            detail = f"recipient refused (SMTP {', '.join(str(code) for code in codes)})"
            if codes and all(_is_permanent(code) for code in codes):
                raise PermanentDeliveryError(detail) from exc
            raise TransientDeliveryError(detail) from exc
        except smtplib.SMTPDataError as exc:
            detail = f"message rejected (SMTP {exc.smtp_code})"
            if _is_permanent(exc.smtp_code):
                raise PermanentDeliveryError(detail) from exc
            raise TransientDeliveryError(detail) from exc
        except smtplib.SMTPResponseException as exc:
            # Authentication and sender problems are ours to fix, not a reason to
            # give up on the message.
            raise TransientDeliveryError(f"{type(exc).__name__} (SMTP {exc.smtp_code})") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise TransientDeliveryError(f"{type(exc).__name__}: {exc}") from exc


class LogEmailSender:
    """Writes the message to the log instead of sending it."""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email (log provider, not sent)",
            extra={
                "to": message["To"],
                "subject": message["Subject"],
                "message_id": message["Message-ID"],
                "body": message.get_content(),
            },
        )


class InMemoryEmailSender:
    """Test double: keeps sent messages and can be scripted to fail."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        # Exceptions raised by the next calls to send(), in order.
        self.failures: list[BaseException] = []

    def send(self, message: EmailMessage) -> None:
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append(message)
