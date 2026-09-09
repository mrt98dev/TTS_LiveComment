from __future__ import annotations

import itertools
import threading
import time

from cmtspeak.connectors.base import CONNECTED, DISCONNECTED, Connector
from cmtspeak.models import Comment
from cmtspeak.queue_bus import CommentQueue

SAMPLE_COMMENTS = [
    ("Nguyễn Văn A", "Giá bao nhiêu vậy shop?"),
    ("Trần Thị B", "Còn size M không ạ?"),
    ("Lê Văn C", "Ship về Hà Nội mất mấy ngày?"),
    ("Phạm Thị D", "Cho mình xin link đặt hàng với"),
    ("Hoàng Văn E", "Sản phẩm này dùng có tốt không mọi người?"),
]


class MockConnector(Connector):
    """Emits sample comments on a fixed interval, standing in for a real
    platform connection during development and testing of the
    queue -> TTS -> audio -> UI pipeline."""

    def __init__(self, queue: CommentQueue, interval_seconds: float = 2.0) -> None:
        super().__init__(queue)
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status_changed.emit(CONNECTED, "")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1)
        self.status_changed.emit(DISCONNECTED, "")

    def _run(self) -> None:
        for author, text in itertools.cycle(SAMPLE_COMMENTS):
            if self._stop_event.wait(self._interval):
                return
            self._queue.put(Comment(platform="mock", author=author, text=text, ts=time.time()))
