"""Process-wide dependencies of the worker: settings, database engine, email sender.

Built lazily on first use so that importing the actors module (which Dramatiq
does in every worker process) does not open connections by itself.
"""

import threading
from dataclasses import dataclass

from sqlalchemy import Engine

from parcelpulse_worker.config import Settings, get_settings
from parcelpulse_worker.db import create_db_engine
from parcelpulse_worker.senders import EmailSender, LogEmailSender, SmtpEmailSender


@dataclass(frozen=True, slots=True)
class Runtime:
    settings: Settings
    engine: Engine
    sender: EmailSender


_runtime: Runtime | None = None
_lock = threading.Lock()


def build_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "log":
        return LogEmailSender()
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
        starttls=settings.smtp_starttls,
        timeout=settings.smtp_timeout_seconds,
    )


def get_runtime() -> Runtime:
    global _runtime
    with _lock:
        if _runtime is None:
            settings = get_settings()
            _runtime = Runtime(
                settings=settings,
                engine=create_db_engine(settings.database_url),
                sender=build_sender(settings),
            )
        return _runtime


def set_runtime(runtime: Runtime | None) -> None:
    """Replace the runtime (tests), or clear it so the next use rebuilds it."""
    global _runtime
    with _lock:
        _runtime = runtime
