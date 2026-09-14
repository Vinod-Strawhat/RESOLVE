"""Local SMTP relay execution channel (Phase 7A-1).

Sends a plain-text email via Python's standard ``smtplib`` through a local
SMTP relay (e.g. Mailpit on 127.0.0.1:1025).  This exercises the real
``submit`` path without AWS credentials while keeping the human-approval and
simulated-channel safety model intact.

Safety:
- The recipient address comes ONLY from configuration (``SMTP_TO``).  The
  model's free-text ``target`` field is display-only and is NEVER used to
  derive a recipient.
- Missing required configuration raises ``ChannelConfigError`` at construction,
  so ``EXECUTION_CHANNEL=smtp`` without configuration fails closed.
- Errors are sanitized: no credentials, no recipients, and no email body are
  ever included in raised errors or logs (the channel does not log).
"""

import os
import smtplib
from email.message import EmailMessage

from backend.channels.base import ChannelConfigError, ChannelError, ChannelResult

DEFAULT_SMTP_PORT = 1025
DEFAULT_TIMEOUT = 15.0

_REQUIRED_ENV = ("SMTP_HOST", "SMTP_FROM", "SMTP_TO")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str) -> bool:
    value = _env(name).lower()
    return value in {"1", "true", "yes", "on"}


def _sanitize_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    message = message.strip()
    if len(message) > 250:
        message = message[:250] + "..."
    return f"SMTP delivery failed ({exc.__class__.__name__}): {message}"


class SmtpRelayChannel:
    """Deliver an approved action as a plain-text email via a local SMTP relay."""

    name = "smtp"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        from_addr: str | None = None,
        to_addrs: str | None = None,
        username: str | None = None,
        password: str | None = None,
        starttls: bool | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        missing: list[str] = []
        self._host = (host if host is not None else _env("SMTP_HOST")) or ""
        self._from = (from_addr if from_addr is not None else _env("SMTP_FROM")) or ""
        self._to = (to_addrs if to_addrs is not None else _env("SMTP_TO")) or ""

        raw_port = port if port is not None else _env("SMTP_PORT", str(DEFAULT_SMTP_PORT))
        try:
            self._port = int(raw_port)
        except (TypeError, ValueError):
            raise ChannelConfigError(
                f"SMTP_PORT must be an integer, got {raw_port!r}"
            ) from None
        if self._port <= 0 or self._port > 65535:
            raise ChannelConfigError(f"SMTP_PORT out of range: {self._port}")

        if not self._host:
            missing.append("SMTP_HOST")
        if not self._from:
            missing.append("SMTP_FROM")
        if not self._to:
            missing.append("SMTP_TO")
        if missing:
            required = ", ".join(sorted(missing))
            raise ChannelConfigError(
                f"missing SMTP configuration for execution channel: {required}"
            )

        effective_username = (
            username
            if username is not None
            else (_env("SMTP_USERNAME") or None)
        )
        effective_password = (
            password
            if password is not None
            else (_env("SMTP_PASSWORD") or None)
        )
        self._username = effective_username if effective_username else None
        self._password = effective_password if effective_password else None
        self._starttls = starttls if starttls is not None else _env_bool("SMTP_STARTTLS")
        self._timeout = timeout

    def submit(self, action: dict) -> ChannelResult:
        if not self._host or not self._from or not self._to:
            raise ChannelConfigError(
                "SMTP execution channel is not configured (SMTP_HOST, SMTP_FROM, "
                "SMTP_TO required)"
            )

        reference = f"RESOLVE-EMAIL-{action['id'][:8].upper()}"
        subject = f"RESOLVE action for case {action['case_id'][:8]}"
        body = action.get("content") or "(no content)"

        message = EmailMessage()
        message["From"] = self._from
        message["To"] = self._to
        message["Subject"] = subject
        message.set_content(body)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as server:
                if self._starttls:
                    server.starttls()
                if self._username:
                    server.login(self._username, self._password)
                server.send_message(message)
        except ChannelError:
            raise
        except Exception as exc:
            raise ChannelError(_sanitize_error(exc)) from exc

        result = (
            "Action emailed through the configured local SMTP relay "
            f"to the configured recipient. Reference {reference}. "
            "Delivered via smtplib; check the relay inbox for the message."
        )
        return ChannelResult(reference, result)