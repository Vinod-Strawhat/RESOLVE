"""Helpers for building Strands Agent input from stored conversation messages."""

from backend.services.memory_store import MemoryStore, VALID_ROLES

DEFAULT_HISTORY_LIMIT = 50


def to_agent_transcript(messages: list[dict]) -> list[dict]:
    """Convert chronological stored messages to Strands Agent message format.

    Each stored message has at least keys ``role`` and ``content``; the
    transcript items are shaped as ``{"role": str, "content": [{"text": str}]}``
    which is what the Strands Agent ``prompt`` parameter expects.
    """
    transcript = []
    for message in messages:
        transcript.append(
            {
                "role": message["role"],
                "content": [{"text": message["content"]}],
            }
        )
    return transcript


def load_session_history(
    store: MemoryStore,
    session_id: str,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[dict]:
    """Return ordered user/assistant messages for a session.

    Only application-level messages are returned: user turns and assistant
    responses. Tool internals and reasoning are never stored or surfaced here.
    """
    messages = store.list_messages(session_id, limit=limit)
    return [message for message in messages if message["role"] in VALID_ROLES]