"""Execution channel protocol (Phase 7A-1).

A channel is the integration point between an approved action and the outside
world.  The ``ActionExecutor`` is the ONLY caller of a channel: it calls
``submit`` strictly after ``begin_execution`` succeeds, which in turn only
accepts an ``approved`` action.  Channels never mutate RESOLVE state.

Contract:
- ``submit(action) -> ChannelResult``: deliver the action.
- Returns a durable reference (e.g. an id unique to this delivery) and a
  human-readable result string.
- Raises ``ChannelError`` on delivery failure.  The executor persists the
  sanitized message and leaves the case state untouched.
- ``name`` identifies the channel for persistence/audit.
- Channels must never log secrets or the action content body.
"""

from typing import NamedTuple, Protocol, runtime_checkable


class ChannelResult(NamedTuple):
    """Outcome of a channel ``submit`` call.

    A ``NamedTuple`` so both attribute access (``result.reference``) and
    legacy tuple unpacking (``reference, result = channel.submit(action)``)
    keep working.
    """

    reference: str
    result: str


class ChannelError(Exception):
    """Delivery failed. ``__str__`` must not contain secrets or body content."""


class ChannelConfigError(ChannelError):
    """The channel is not usable because its configuration is incomplete."""


@runtime_checkable
class Channel(Protocol):
    """Protocol implemented by every execution channel."""

    name: str

    def submit(self, action: dict) -> ChannelResult:
        """Deliver the action and return a reference + result, or raise."""
        ...