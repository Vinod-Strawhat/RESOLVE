"""Simulated execution channel (default, Phase 7A-1).

Safe, clearly-labeled simulated execution used for development and testing.
Produces a stable reference without making any external request.
"""

from backend.channels.base import ChannelResult


class SimulatedExecutionChannel:
    """Deliver without any external side effect.

    Produces a stable execution reference and a human-readable result that
    explicitly states that nothing was actually sent.
    """

    name = "simulated"

    def submit(self, action: dict) -> ChannelResult:
        reference = f"RESOLVE-ACTION-{action['id'][:8].upper()}"
        result = (
            "Action submitted through the configured simulated support channel. "
            f"Reference {reference}. This is a simulated execution; nothing was "
            "actually sent to any external party."
        )
        return ChannelResult(reference, result)