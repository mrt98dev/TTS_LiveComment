from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget

from cmtspeak.config import Config
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.tts.worker import TTSWorker
from cmtspeak.ui.log_panel import LogPanel
from cmtspeak.ui.theme import load_icon

_QUEUE_SIZE_POLL_INTERVAL_MS = 500


class PlaybackControls(QWidget):
    """Tạm dừng/Bỏ qua/Xóa hàng đợi — moved out of MainWindow so the Live page
    can be assembled independently. Behavior is unchanged from the previous
    inline implementation: only the widget wrapping and icon+text styling
    changed."""

    def __init__(
        self,
        worker: TTSWorker,
        cfg: Config,
        queue: CommentQueue,
        log_panel: LogPanel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._worker = worker
        self._cfg = cfg
        self._queue = queue
        self._log_panel = log_panel

        self.pause_button = QPushButton(load_icon("pause"), "Tạm dừng đọc")
        self.pause_button.setCheckable(True)
        self.pause_button.toggled.connect(self._on_pause_toggled)

        self.skip_button = QPushButton(load_icon("skip-forward"), "Bỏ qua")
        self.skip_button.clicked.connect(self._on_skip_clicked)

        self.clear_queue_button = QPushButton(load_icon("trash-2"), "Xóa hàng đợi")
        self.clear_queue_button.clicked.connect(self._on_clear_queue_clicked)

        self.queue_size_badge = QLabel()
        self.queue_size_badge.setProperty("class", "status-pill")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pause_button)
        layout.addWidget(self.skip_button)
        layout.addWidget(self.clear_queue_button)
        layout.addStretch(1)
        layout.addWidget(self.queue_size_badge)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_QUEUE_SIZE_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._update_queue_size_badge)
        self._poll_timer.start()
        self._update_queue_size_badge()

    def _update_queue_size_badge(self) -> None:
        self.queue_size_badge.setText(f"{self._queue.size} đang chờ")

    def _on_pause_toggled(self, checked: bool) -> None:
        if checked:
            self._worker.pause()
            self.pause_button.setIcon(load_icon("play"))
            self.pause_button.setText("Tiếp tục đọc")
        else:
            self._worker.resume()
            self.pause_button.setIcon(load_icon("pause"))
            self.pause_button.setText("Tạm dừng đọc")

    def _on_skip_clicked(self) -> None:
        """"Bỏ qua" behaves according to Config's skip_mode: either interrupt
        whatever is currently playing (worker moves on to the next queued
        comment on its own) or drop just the oldest still-waiting comment
        without touching anything already playing. Either mode is a safe
        no-op when there is nothing to skip."""
        skip_mode = self._cfg.get("skip_mode")
        if skip_mode == "next_only":
            comment = self._queue.pop_next()
            if comment is not None:
                self._log_panel.mark_removed([comment], reason="đã bỏ qua")
        else:
            self._worker.skip_current(interrupt=True)
        self._update_queue_size_badge()

    def _on_clear_queue_clicked(self) -> None:
        answer = QMessageBox.question(
            self,
            "Xóa hàng đợi",
            "Xóa toàn bộ các bình luận đang chờ đọc? Không thể hoàn tác.",
        )
        if answer != QMessageBox.Yes:
            return
        removed = self._queue.clear()
        if removed:
            self._log_panel.mark_removed(removed, reason="đã xóa")
        self._update_queue_size_badge()
