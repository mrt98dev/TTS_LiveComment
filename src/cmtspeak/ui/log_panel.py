from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from cmtspeak.models import Comment
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.ui.theme import PALETTE

_BASE_TEXT_ROLE = Qt.UserRole
_STATUS_ROLE = Qt.UserRole + 1
_PLATFORM_ROLE = Qt.UserRole + 2


class ReadStatus(Enum):
    PENDING = auto()
    READING = auto()
    READ = auto()
    REMOVED = auto()


_STATUS_COLOR = {
    ReadStatus.PENDING: PALETTE["status_pending"],
    ReadStatus.READING: PALETTE["accent"],
    ReadStatus.READ: PALETTE["text_muted"],
    ReadStatus.REMOVED: PALETTE["status_error"],
}

_TEXT_COLOR = {
    ReadStatus.PENDING: PALETTE["text_secondary"],
    ReadStatus.READING: PALETTE["text_primary"],
    ReadStatus.READ: PALETTE["text_muted"],
    ReadStatus.REMOVED: PALETTE["status_error"],
}

_PLATFORM_BADGE = {"tiktok": "TT", "youtube": "YT", "mock": "MK"}
_PLATFORM_COLOR = {
    "tiktok": PALETTE["platform_tiktok"],
    "youtube": PALETTE["platform_youtube"],
    "mock": PALETTE["text_muted"],
}


class _CommentItemDelegate(QStyledItemDelegate):
    """Paints a colored left border (comment status) and a small platform
    badge (TT/YT/MK) before each row's text, instead of the old emoji-prefix
    approach — QListWidgetItem alone can't draw a per-edge border or a
    rounded badge, so this delegate handles just those two extras and hands
    everything else (text, selection highlight) to the default painting."""

    _BORDER_WIDTH = 3
    _BADGE_WIDTH = 26
    _BADGE_HEIGHT = 16
    _GAP = 6

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:  # noqa: N802 - Qt override
        status = index.data(_STATUS_ROLE)
        platform = index.data(_PLATFORM_ROLE)

        painter.save()
        border_color = QColor(_STATUS_COLOR.get(status, PALETTE["text_muted"]))
        painter.fillRect(
            QRect(option.rect.x(), option.rect.y(), self._BORDER_WIDTH, option.rect.height()),
            border_color,
        )

        badge_rect = QRect(
            option.rect.x() + self._BORDER_WIDTH + self._GAP,
            option.rect.y() + (option.rect.height() - self._BADGE_HEIGHT) // 2,
            self._BADGE_WIDTH,
            self._BADGE_HEIGHT,
        )
        badge_color = QColor(_PLATFORM_COLOR.get(platform, PALETTE["text_muted"]))
        painter.setPen(Qt.NoPen)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(badge_rect, 8, 8)

        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge_rect, Qt.AlignCenter, _PLATFORM_BADGE.get(platform, "?"))
        painter.restore()

        text_option = QStyleOptionViewItem(option)
        text_offset = self._BORDER_WIDTH + self._GAP + self._BADGE_WIDTH + self._GAP
        text_option.rect = option.rect.adjusted(text_offset, 0, 0, 0)
        super().paint(painter, text_option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index):  # noqa: N802 - Qt override
        size = super().sizeHint(option, index)
        size.setWidth(size.width() + self._BORDER_WIDTH + self._GAP + self._BADGE_WIDTH + self._GAP)
        return size


class LogPanel(QWidget):
    """Realtime scrolling view of every comment received, independent of how
    fast the TTS worker is actually reading them. Each row's status (chờ
    đọc/đang đọc/đã đọc/đã bỏ) is shown via a colored left border painted by
    `_CommentItemDelegate`, driven by `_STATUS_ROLE` — not by any prefix in
    the item's own text.

    Relies on TTSWorker emitting now_reading then finished_reading exactly
    once each, in order, for every comment it takes off the queue —
    matched against the shared queue's own strict FIFO order (comments
    arrive here via the same queue, in the same order the worker consumes
    them) to know which displayed row a given signal refers to.
    """

    def __init__(self, queue: CommentQueue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue = queue
        self._pending_items: list[QListWidgetItem] = []

        self.list_widget = QListWidget()
        self.list_widget.setItemDelegate(_CommentItemDelegate(self.list_widget))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_widget)

        queue.comment_received.connect(self.add_comment)

    def add_comment(self, comment: Comment) -> None:
        base_text = f"{comment.author}: {comment.text}"

        item = QListWidgetItem()
        item.setData(_BASE_TEXT_ROLE, base_text)
        item.setData(_PLATFORM_ROLE, comment.platform)
        self._set_status(item, ReadStatus.PENDING)

        self.list_widget.addItem(item)
        self._pending_items.append(item)
        self.list_widget.scrollToBottom()

    def set_now_reading(self, _comment: Comment) -> None:
        """Called when the TTS worker starts speaking the next comment. Since
        the worker consumes the same queue strictly FIFO, the oldest item
        still pending is always the one now being read — only peeked here
        (not removed) so set_finished_reading can later mark this exact
        item as done."""
        if self._pending_items:
            item = self._pending_items[0]
            self._set_status(item, ReadStatus.READING)
            self.list_widget.scrollToItem(item)

    def set_finished_reading(self, _comment: Comment) -> None:
        """Called once the worker is done with a comment — spoken, skipped,
        or failed. Marks it read and stops tracking it, so a later
        now_reading correctly points at the next one."""
        if self._pending_items:
            item = self._pending_items.pop(0)
            self._set_status(item, ReadStatus.READ)

    def set_filtered(self, _comment: Comment, reason: str) -> None:
        """Called when the worker decides not to speak a comment after all —
        a blocklist match (in "skip" mode) or a detected duplicate. The row
        was already marked READING by set_now_reading right before this, so
        this replaces that with a distinct removed state (reason appended to
        the text) instead of the normal "đã đọc", and stops tracking it the
        same way set_finished_reading does (pop the front of
        _pending_items) — a comment always gets exactly one of
        set_finished_reading/set_filtered, never both, matching TTSWorker's
        signal contract."""
        if self._pending_items:
            item = self._pending_items.pop(0)
            self._set_status(item, ReadStatus.REMOVED, reason=reason)

    def mark_removed(self, comments: list[Comment], reason: str = "đã xóa") -> None:
        """Mark comments pulled straight off the front of the shared queue
        (not through the normal now_reading/finished_reading flow) as
        removed — used both by "Xóa hàng đợi" (queue.clear()) and by the
        "next_only" skip mode (queue.pop_next()). `comments` always lines up
        with the oldest still-*pending* rows in arrival order, so rather than
        matching by identity we just walk `_pending_items` in order and mark
        the first `len(comments)` rows that aren't the one currently
        READING — that row was already taken off the queue by the worker's
        own get(), so it can never be among `comments`, and it must be left
        untouched here rather than blindly popped from the front."""
        if not comments:
            return
        remaining: list[QListWidgetItem] = []
        to_remove = len(comments)
        removed = 0
        for item in self._pending_items:
            if removed < to_remove and item.data(_STATUS_ROLE) != ReadStatus.READING:
                self._set_status(item, ReadStatus.REMOVED, reason=reason)
                removed += 1
                continue
            remaining.append(item)
        self._pending_items = remaining

    def _set_status(self, item: QListWidgetItem, status: ReadStatus, reason: str | None = None) -> None:
        base_text = item.data(_BASE_TEXT_ROLE)
        item.setData(_STATUS_ROLE, status)
        text = f"{base_text} — {reason}" if status == ReadStatus.REMOVED and reason else base_text
        item.setText(text)

        font = item.font()
        font.setBold(status == ReadStatus.READING)
        item.setFont(font)
        item.setForeground(QColor(_TEXT_COLOR[status]))

