from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from cmtspeak.ui.theme import PALETTE

_MARGIN = 16
_GAP = 8
_WIDTH = 320
_DEFAULT_DURATION_MS = 4000

_LEVEL_COLOR = {
    "error": PALETTE["status_error"],
    "warning": PALETTE["status_pending"],
}

_active_toasts: list["_ToastWidget"] = []


class _ToastWidget(QWidget):
    """A single auto-dismissing notification, shown as its own frameless
    top-level window (not a child widget) so it floats above everything
    at a fixed screen position regardless of the main window's size or
    layout — showing it inline would grow whatever layout it sits in."""

    def __init__(self, text: str, level: str) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        accent = _LEVEL_COLOR.get(level, PALETTE["accent"])
        self.setFixedWidth(_WIDTH)
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {PALETTE["bg_card"]};
                border: 1px solid {PALETTE["border"]};
                border-left: 4px solid {accent};
                border-radius: 8px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {PALETTE["text_primary"]};
                font-size: 12px;
            }}
            """
        )

        label = QLabel(text)
        label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(label)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override signature
        if self in _active_toasts:
            _active_toasts.remove(self)
        super().closeEvent(event)


def show_toast(
    text: str,
    level: str = "error",
    duration_ms: int = _DEFAULT_DURATION_MS,
    parent_widget: QWidget | None = None,
) -> None:
    """Pop up a toast at the top-right of the screen (the one the app's
    window is on, if `parent_widget` is given) for `duration_ms`, then it
    closes itself. Stacks below any toast already showing rather than
    overlapping it; does not reflow the stack when an earlier one closes
    first — acceptable since toasts are short-lived."""
    toast = _ToastWidget(text, level)
    toast.adjustSize()

    screen = parent_widget.screen() if parent_widget is not None else None
    if screen is None:
        screen = QApplication.primaryScreen()
    geometry = screen.availableGeometry()

    y = geometry.top() + _MARGIN
    for existing in _active_toasts:
        y += existing.height() + _GAP
    x = geometry.right() - toast.width() - _MARGIN
    toast.move(x, y)

    _active_toasts.append(toast)
    toast.show()
    QTimer.singleShot(duration_ms, toast.close)
