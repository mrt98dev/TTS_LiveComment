from __future__ import annotations

import queue
from typing import Optional

from PySide6.QtCore import QObject, Signal

from cmtspeak.models import Comment


class CommentQueue(QObject):
    """Thread-safe FIFO queue of Comments, shared by every connector and consumed
    by the TTS worker. put() may be called from any thread; comment_received is
    delivered to slots on the thread they were connected from (Qt auto-connection),
    so UI code can update safely without extra locking."""

    comment_received = Signal(Comment)

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue[Comment] = queue.Queue()

    def put(self, comment: Comment) -> None:
        self._queue.put(comment)
        self.comment_received.emit(comment)

    def get(self, timeout: float | None = None) -> Comment:
        return self._queue.get(timeout=timeout)

    def clear(self) -> list[Comment]:
        """Drain every comment currently waiting (not the one already handed
        to a consumer via get()) and return them in FIFO order. Safe to call
        while a worker thread is concurrently blocked in get() — relies on
        queue.Queue's own internal locking, no extra synchronization needed."""
        drained: list[Comment] = []
        while True:
            try:
                drained.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return drained

    def pop_next(self) -> Optional[Comment]:
        """Remove and return exactly the oldest still-waiting comment (FIFO
        front), or None if the queue is empty. Same non-interference contract
        as clear() — never touches an item already handed to a concurrent
        get() call."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    @property
    def size(self) -> int:
        return self._queue.qsize()
