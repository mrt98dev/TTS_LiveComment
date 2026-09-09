from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cmtspeak.audio.output import AudioOutput
from cmtspeak.config import Config
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.tts.filter import CommentFilter
from cmtspeak.tts.voice_manager import VoiceManager
from cmtspeak.tts.worker import TTSWorker
from cmtspeak.ui.connection_panel import ConnectionPanel
from cmtspeak.ui.filter_page import FilterPage
from cmtspeak.ui.general_page import GeneralPage
from cmtspeak.ui.log_panel import LogPanel
from cmtspeak.ui.playback_controls import PlaybackControls
from cmtspeak.ui.theme import PALETTE, load_icon
from cmtspeak.ui.voices_page import VoicesPage

APP_VERSION = "0.1.0"

_NAV_ITEMS = [
    ("Live", "radio"),
    ("Giọng đọc", "mic-2"),
    ("Bộ lọc nội dung", "filter"),
    ("Chung", "settings"),
]

_SIDEBAR_WIDTH = 200


class MainWindow(QMainWindow):
    """Cửa sổ duy nhất của app: sidebar trái điều hướng 4 trang (Live/Giọng
    đọc/Bộ lọc nội dung/Chung) hiển thị qua một QStackedWidget, thay cho mô
    hình cũ (cửa sổ chính gọn + dialog "Cài đặt" riêng mở từ menu bar). Mỗi
    trang cấu hình tự lưu vào Config ngay khi người dùng đổi giá trị — không
    còn nút "Lưu cài đặt" tổng."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("cmt-speak")
        self.resize(1000, 640)

        self.cfg = Config()
        self.queue = CommentQueue()
        self.voice_manager = VoiceManager(self.cfg)
        self.audio_output = AudioOutput()
        self.comment_filter = CommentFilter(self.cfg)
        self.worker = TTSWorker(self.queue, self.voice_manager, self.cfg, self.audio_output, self.comment_filter)

        self.connection_panel = ConnectionPanel(self.queue, self.cfg)
        self.log_panel = LogPanel(self.queue)
        self.playback_controls = PlaybackControls(self.worker, self.cfg, self.queue, self.log_panel)
        self.voices_page = VoicesPage(self.cfg, self.voice_manager, self.audio_output)
        self.filter_page = FilterPage(self.cfg)
        self.general_page = GeneralPage(self.cfg)

        self.worker.now_reading.connect(self.log_panel.set_now_reading)
        self.worker.finished_reading.connect(self.log_panel.set_finished_reading)
        self.worker.comment_filtered.connect(self.log_panel.set_filtered)
        self.worker.warning.connect(self._on_worker_warning)

        self._build_menu()
        self._build_central_widget()

        self.worker.start()

    def _build_central_widget(self) -> None:
        live_page = QWidget()
        live_layout = QVBoxLayout(live_page)
        live_layout.addWidget(self.connection_panel)
        live_layout.addWidget(self.playback_controls)
        live_layout.addWidget(self.log_panel, stretch=1)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(live_page)
        self.stacked_widget.addWidget(self.voices_page)
        self.stacked_widget.addWidget(self.filter_page)
        self.stacked_widget.addWidget(self.general_page)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self.stacked_widget, stretch=1)
        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setProperty("class", "sidebar")
        sidebar.setFixedWidth(_SIDEBAR_WIDTH)

        nav_group = QButtonGroup(sidebar)
        nav_group.setExclusive(True)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        for index, (label, icon_name) in enumerate(_NAV_ITEMS):
            button = QToolButton()
            button.setProperty("class", "nav-item")
            button.setCheckable(True)
            button.setText(label)
            button.setIcon(load_icon(icon_name, PALETTE["text_secondary"]))
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.clicked.connect(lambda _checked, i=index: self.stacked_widget.setCurrentIndex(i))
            nav_group.addButton(button)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)

        layout.addStretch(1)

        version_label = QLabel(f"cmt-speak v{APP_VERSION}")
        version_label.setProperty("class", "hint")
        layout.addWidget(version_label)

        return sidebar

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("cmt-speak")
        menu.addAction("Giới thiệu", self._on_show_about)
        menu.addAction("Thoát", self.close)

    def _on_show_about(self) -> None:
        QMessageBox.about(
            self,
            "Giới thiệu",
            f"<b>cmt-speak</b> — phiên bản {APP_VERSION}<br>"
            "Đọc bình luận TikTok/YouTube Live bằng giọng nói tiếng Việt "
            "tổng hợp cục bộ (VieNeu-TTS).",
        )

    def _on_worker_warning(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override signature
        self.connection_panel.stop_all()
        self.worker.stop()
        self.worker.wait(2000)
        self.voices_page.shutdown()
        super().closeEvent(event)
