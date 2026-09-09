from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from cmtspeak.config import Config
from cmtspeak.connectors.base import CONNECTED, CONNECTING, Connector, DISCONNECTED, ERROR, RECONNECTING
from cmtspeak.connectors.tiktok_connector import TikTokConnector
from cmtspeak.connectors.youtube_connector import YouTubeConnector
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.ui.theme import PALETTE, load_icon
from cmtspeak.ui.toast import show_toast

_STATUS_LABELS = {
    CONNECTING: "Đang kết nối...",
    CONNECTED: "Đã kết nối",
    RECONNECTING: "Đang kết nối lại",
    DISCONNECTED: "Chưa kết nối",
    ERROR: "Lỗi",
}

_STATUS_PROPERTY = {
    CONNECTING: "connecting",
    CONNECTED: "connected",
    RECONNECTING: "reconnecting",
    DISCONNECTED: "disconnected",
    ERROR: "error",
}

# Keeps the pill a fixed width no matter how long a status/error message
# gets — the full message goes to the pill's tooltip and (for a genuine
# error) a toast, never into the pill's own text.
_STATUS_PILL_MAX_WIDTH = 150


class ConnectorRow(QWidget):
    """One platform's connect/disconnect control: a text input plus a toggle
    button and a status label. Independent of any other row — connecting or
    losing one platform never touches the other."""

    def __init__(
        self,
        placeholder: str,
        make_connector: Callable[[str], Optional[Connector]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._make_connector = make_connector
        self._connector: Optional[Connector] = None
        self._last_status = DISCONNECTED

        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.button = QPushButton("Kết nối")
        self.status_label = QLabel(_STATUS_LABELS[DISCONNECTED])
        self.status_label.setProperty("class", "status-pill")
        self.status_label.setProperty("status", _STATUS_PROPERTY[DISCONNECTED])
        self.status_label.setMaximumWidth(_STATUS_PILL_MAX_WIDTH)

        self.button.clicked.connect(self._on_button_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.input, stretch=2)
        layout.addWidget(self.button)
        layout.addWidget(self.status_label, stretch=1)

    def _on_button_clicked(self) -> None:
        if self._connector is None:
            self._connect()
        else:
            self._disconnect()

    def _connect(self) -> None:
        text = self.input.text().strip()
        if not text:
            self.show_error("Vui lòng nhập thông tin trước khi kết nối")
            return

        connector = self._make_connector(text)
        if connector is None:
            # make_connector already reported why (e.g. missing API key).
            return

        connector.status_changed.connect(self._on_status_changed)
        self._connector = connector
        self.input.setEnabled(False)
        self.button.setText("Ngắt kết nối")
        connector.start()

    def _disconnect(self) -> None:
        if self._connector is not None:
            self._connector.stop()
        self._reset()

    def _reset(self) -> None:
        self._connector = None
        self.input.setEnabled(True)
        self.button.setText("Kết nối")
        self._set_status_pill(DISCONNECTED, _STATUS_LABELS[DISCONNECTED])
        self.status_label.setToolTip("")
        self._last_status = DISCONNECTED

    def _set_status_pill(self, status: str, text: str) -> None:
        """Update both the pill's text and its `status` property (used by the
        QSS in ui/theme.py to color it) — a property change alone doesn't
        repaint until the widget's style is unpolished/repolished.

        The pill always shows the short fixed label from _STATUS_LABELS,
        never a variable-length message — that's what used to make long
        error/reconnect text stretch the whole window. Elided defensively
        on top of that in case a caller ever passes something longer."""
        metrics = self.status_label.fontMetrics()
        elided = metrics.elidedText(text, Qt.ElideRight, _STATUS_PILL_MAX_WIDTH - 16)
        self.status_label.setText(elided)
        self.status_label.setProperty("status", _STATUS_PROPERTY.get(status, "disconnected"))
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def show_error(self, message: str) -> None:
        """Surface a message that isn't itself a connector status transition
        (e.g. a local input-validation error) without touching the status
        pill's fixed-width text — same toast + tooltip treatment as a real
        connector error."""
        self.status_label.setToolTip(message)
        show_toast(message, level="error", parent_widget=self)

    def _on_status_changed(self, status: str, message: str) -> None:
        self._set_status_pill(status, _STATUS_LABELS.get(status, status))
        self.status_label.setToolTip(message)

        if message and status != self._last_status:
            # Only toast on the transition into this status, not on every
            # repeated emission of it (RECONNECTING fires again on every
            # backoff attempt with an updated message) — the tooltip still
            # always reflects the latest message for anyone who hovers.
            level = "error" if status == ERROR else "warning"
            show_toast(message, level=level, parent_widget=self)
        self._last_status = status

        if status in (DISCONNECTED, ERROR):
            # The connector reported a terminal state on its own (live ended,
            # connection dropped, API error) — reflect that in the UI without
            # waiting for the user to click "Ngắt kết nối".
            self._connector = None
            self.input.setEnabled(True)
            self.button.setText("Kết nối")

    def stop(self) -> None:
        """Stop any active connection without touching UI state further than
        needed — used when the whole window is closing."""
        if self._connector is not None:
            self._connector.stop()
            self._connector = None


class ConnectionPanel(QWidget):
    """TikTok and YouTube connection controls, each independent so both can
    be connected at the same time and feed the same shared CommentQueue."""

    def __init__(self, queue: CommentQueue, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue = queue
        self._cfg = cfg

        self.tiktok_row = ConnectorRow("Username TikTok", self._make_tiktok_connector)
        self.youtube_row = ConnectorRow("URL hoặc ID video YouTube Live", self._make_youtube_connector)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_platform_card("TikTok Live", "plug", self.tiktok_row))
        layout.addWidget(self._build_platform_card("YouTube Live", "plug", self.youtube_row))

    @staticmethod
    def _build_platform_card(title: str, icon_name: str, row: "ConnectorRow") -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")

        icon_label = QLabel()
        icon_label.setPixmap(load_icon(icon_name, PALETTE["text_secondary"]).pixmap(18, 18))

        title_row = QHBoxLayout()
        title_row.addWidget(icon_label)
        title_row.addWidget(QLabel(f"<b>{title}</b>"))
        title_row.addStretch(1)

        layout = QVBoxLayout(card)
        layout.addLayout(title_row)
        layout.addWidget(row)
        return card

    def _make_tiktok_connector(self, username: str) -> Optional[Connector]:
        return TikTokConnector(self._queue, username)

    def _make_youtube_connector(self, video_id_or_url: str) -> Optional[Connector]:
        api_key = self._cfg.get("youtube_api_key")
        if not api_key:
            self.youtube_row.show_error("Chưa có YouTube API key — vui lòng nhập trong Cài đặt")
            return None
        return YouTubeConnector(self._queue, api_key, video_id_or_url)

    def stop_all(self) -> None:
        self.tiktok_row.stop()
        self.youtube_row.stop()
