from __future__ import annotations


def customer_safe_message(message: object | None, fallback: str) -> str:
    """Return non-empty customer guidance without assuming a handler's message type."""

    if isinstance(message, str) and message.strip():
        return message.strip()
    return fallback