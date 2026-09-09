from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from cmtspeak.queue_bus import CommentQueue

# Status values a Connector can report via status_changed.
CONNECTING = "connecting"
CONNECTED = "connected"
RECONNECTING = "reconnecting"
ERROR = "error"
DISCONNECTED = "disconnected"

# Backoff schedule (seconds) for auto-reconnect attempts: 2s, 5s, 10s, 30s,
# then holds at 30s for every attempt after that. Retries are unlimited
# (no cap on `attempt`) per the design's explicit choice not to give up.
_BACKOFF_SCHEDULE_SECONDS = (2.0, 5.0, 10.0, 30.0)


def next_backoff_delay(attempt: int) -> float:
    """Pure function: how long to wait (seconds) before reconnect `attempt`
    (1-indexed - the first retry is attempt 1). Follows the fixed schedule
    2s -> 5s -> 10s -> 30s, then stays at 30s for attempt 5 and beyond."""
    index = max(attempt, 1) - 1
    index = min(index, len(_BACKOFF_SCHEDULE_SECONDS) - 1)
    return _BACKOFF_SCHEDULE_SECONDS[index]


class Connector(QObject):
    """Base interface for a live-comment source. A Connector owns its own
    background thread/event loop, normalizes platform-specific events into
    Comment objects, and pushes them into the shared CommentQueue. Connectors
    never talk to each other or drop comments; on failure they report status
    and stop, they do not auto-reconnect (MVP)."""

    status_changed = Signal(str, str)  # (status, message)

    def __init__(self, queue: CommentQueue) -> None:
        super().__init__()
        self._queue = queue

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError
