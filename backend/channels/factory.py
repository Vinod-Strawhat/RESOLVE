"""Execution channel selection (Phase 7A-1).

The running channel is chosen by the ``EXECUTION_CHANNEL`` environment
variable:
- ``simulated`` (default when unset): the simulated channel, no external side
  effects.
- ``smtp``: a local SMTP relay via smtplib.  Requires SMTP_HOST/SMTP_FROM/
  SMTP_TO; missing configuration fails closed.

Unknown values NEVER silently fall back to simulated: they raise
``ChannelConfigError`` so execution is blocked rather than unexpectedly going
out over a real channel.
"""

import os

from backend.channels.base import Channel, ChannelConfigError
from backend.channels.simulated import SimulatedExecutionChannel
from backend.channels.smtp import SmtpRelayChannel

SUPPORTED_CHANNELS = ("simulated", "smtp")
DEFAULT_CHANNEL = "simulated"


def get_configured_channel_name() -> str:
    raw = os.environ.get("EXECUTION_CHANNEL", "").strip().lower()
    if not raw:
        return DEFAULT_CHANNEL
    if raw not in SUPPORTED_CHANNELS:
        raise ChannelConfigError(
            f"unknown EXECUTION_CHANNEL {raw!r}; supported: "
            f"{', '.join(SUPPORTED_CHANNELS)}"
        )
    return raw


def is_real_channel(name: str) -> bool:
    """A real channel produces external side effects (e.g. actually emails)."""
    return name == "smtp"


def build_channel() -> Channel:
    name = get_configured_channel_name()
    if name == "simulated":
        return SimulatedExecutionChannel()
    if name == "smtp":
        return SmtpRelayChannel()
    raise ChannelConfigError(
        f"unable to build execution channel {name!r}; "
        f"supported: {', '.join(SUPPORTED_CHANNELS)}"
    )