"""Execution channels (Phase 7A-1).

Public surface:
- protocols/result types: :mod:`backend.channels.base`
- implemented channels: :mod:`backend.channels.simulated`,
  :mod:`backend.channels.smtp`
- configuration/factory: :mod:`backend.channels.factory`
"""

from backend.channels.base import Channel, ChannelConfigError, ChannelError, ChannelResult
from backend.channels.factory import (
    build_channel,
    get_configured_channel_name,
    is_real_channel,
)
from backend.channels.simulated import SimulatedExecutionChannel
from backend.channels.smtp import SmtpRelayChannel

__all__ = [
    "Channel",
    "ChannelConfigError",
    "ChannelError",
    "ChannelResult",
    "SimulatedExecutionChannel",
    "SmtpRelayChannel",
    "build_channel",
    "get_configured_channel_name",
    "is_real_channel",
]