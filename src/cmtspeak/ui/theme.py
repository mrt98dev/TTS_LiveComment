from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

PALETTE: dict[str, str] = {
    "bg_window": "#0f1115",
    "bg_sidebar": "#161922",
    "bg_card": "#1c1f29",
    "border": "#2a2e3a",
    "text_primary": "#e6e8ee",
    "text_secondary": "#9198a8",
    "text_muted": "#5b6172",
    "accent": "#6c5ce7",
    "status_success": "#22c55e",
    "status_pending": "#f5a623",
    "status_error": "#ef4444",
    "platform_tiktok": "#ff2d55",
    "platform_youtube": "#ff0000",
}


@lru_cache(maxsize=None)
def _rendered_icon(name: str, color: str, size: int) -> QIcon:
    path = ICONS_DIR / f"{name}.svg"
    if not path.exists():
        return QIcon()

    svg_data = path.read_text(encoding="utf-8").replace("currentColor", color)

    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


def load_icon(name: str, color: str = PALETTE["text_primary"], size: int = 20) -> QIcon:
    """Load one of the bundled SVG icons (see assets/icons/), recolored to
    `color` by substituting the `currentColor` placeholder baked into every
    icon file. Returns an empty (null) QIcon for an unknown name rather than
    raising, since a missing icon shouldn't crash the app."""
    return _rendered_icon(name, color, size)


STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {PALETTE["bg_window"]};
    color: {PALETTE["text_primary"]};
    font-size: 13px;
}}

QLabel[class="hint"] {{
    color: {PALETTE["text_secondary"]};
    font-size: 11px;
}}

QLabel[class="section-title"] {{
    font-size: 15px;
    font-weight: 600;
}}

QFrame[class="card"] {{
    background-color: {PALETTE["bg_card"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 8px;
}}

QLineEdit, QComboBox, QSpinBox, QListWidget {{
    background-color: {PALETTE["bg_window"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 6px;
    padding: 4px 8px;
    color: {PALETTE["text_primary"]};
    selection-background-color: {PALETTE["accent"]};
}}

QLineEdit:disabled {{
    color: {PALETTE["text_muted"]};
}}

QPushButton, QToolButton {{
    background-color: {PALETTE["bg_card"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 6px;
    padding: 6px 12px;
    color: {PALETTE["text_primary"]};
}}

QPushButton:hover, QToolButton:hover {{
    border-color: {PALETTE["accent"]};
}}

QPushButton:pressed, QToolButton:pressed {{
    background-color: {PALETTE["border"]};
}}

QPushButton[class="primary"] {{
    background-color: {PALETTE["accent"]};
    border: none;
}}

QWidget[class="sidebar"] {{
    background-color: {PALETTE["bg_sidebar"]};
}}

QToolButton[class="nav-item"] {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px 12px;
    text-align: left;
    color: {PALETTE["text_secondary"]};
}}

QToolButton[class="nav-item"]:hover {{
    background-color: {PALETTE["border"]};
    color: {PALETTE["text_primary"]};
}}

QToolButton[class="nav-item"]:checked {{
    background-color: #2a2440;
    color: {PALETTE["text_primary"]};
}}

QLabel[class="status-pill"] {{
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 11px;
    background-color: {PALETTE["border"]};
    color: {PALETTE["text_secondary"]};
}}

QLabel[class="status-pill"][status="connected"] {{
    color: {PALETTE["status_success"]};
}}

QLabel[class="status-pill"][status="connecting"],
QLabel[class="status-pill"][status="reconnecting"] {{
    color: {PALETTE["status_pending"]};
}}

QLabel[class="status-pill"][status="error"] {{
    color: {PALETTE["status_error"]};
}}

QLabel[class="status-pill"][status="disconnected"] {{
    color: {PALETTE["text_secondary"]};
}}
"""
