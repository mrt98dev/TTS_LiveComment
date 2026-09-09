from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cmtspeak.audio.output import list_output_devices
from cmtspeak.config import Config
from cmtspeak.ui.theme import PALETTE, load_icon

TEMPLATE_HINT = (
    "Có thể dùng {name} (tên người bình luận) và {content} (nội dung bình luận) — "
    'vd: "{name} nói: {content}". Phần chữ khác giữ nguyên làm tiền tố/hậu tố.'
)

_TEXT_SAVE_DEBOUNCE_MS = 300

_SKIP_MODE_LABELS: list[tuple[str, str]] = [
    ("Ngắt đọc ngay", "interrupt"),
    ("Chỉ bỏ comment kế tiếp", "next_only"),
]


class GeneralPage(QWidget):
    """Trang "Chung" trong sidebar — trước đây là tab của SettingsPanel. Mọi
    thay đổi lưu vào Config ngay: combo lưu ngay khi đổi lựa chọn, ô nhập
    text lưu sau khi ngừng gõ 300ms (debounce, tránh ghi file mỗi phím
    bấm)."""

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg

        self.device_combo = QComboBox()
        self.refresh_devices_button = QPushButton(load_icon("plug"), "Làm mới")
        self.template_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.skip_mode_combo = QComboBox()
        for label, value in _SKIP_MODE_LABELS:
            self.skip_mode_combo.addItem(label, value)

        self._template_save_timer = QTimer(self)
        self._template_save_timer.setSingleShot(True)
        self._template_save_timer.setInterval(_TEXT_SAVE_DEBOUNCE_MS)
        self._template_save_timer.timeout.connect(self._save_template)

        self._api_key_save_timer = QTimer(self)
        self._api_key_save_timer.setSingleShot(True)
        self._api_key_save_timer.setInterval(_TEXT_SAVE_DEBOUNCE_MS)
        self._api_key_save_timer.timeout.connect(self._save_api_key)

        self._build_layout()
        self._load_from_config()

        self.refresh_devices_button.clicked.connect(self._refresh_device_combo)
        self.device_combo.currentIndexChanged.connect(self._save_device)
        self.skip_mode_combo.currentIndexChanged.connect(self._save_skip_mode)
        self.template_edit.textChanged.connect(lambda _: self._template_save_timer.start())
        self.api_key_edit.textChanged.connect(lambda _: self._api_key_save_timer.start())

    def _build_layout(self) -> None:
        card = QFrame()
        card.setProperty("class", "card")

        title_label = QLabel("Chung")
        title_label.setProperty("class", "section-title")
        title_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(load_icon("settings", PALETTE["text_secondary"]).pixmap(18, 18))
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch(1)

        device_row = QHBoxLayout()
        device_row.addWidget(self.device_combo, stretch=1)
        device_row.addWidget(self.refresh_devices_button)

        template_hint_label = QLabel(TEMPLATE_HINT)
        template_hint_label.setProperty("class", "hint")
        template_hint_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Thiết bị audio output:", device_row)
        form.addRow("Mẫu câu đọc:", self.template_edit)
        form.addRow("", template_hint_label)
        form.addRow("YouTube API key:", self.api_key_edit)
        form.addRow('Hành vi nút "Bỏ qua":', self.skip_mode_combo)

        layout = QVBoxLayout(self)
        card_layout = QVBoxLayout(card)
        card_layout.addLayout(title_row)
        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch(1)

    def _load_from_config(self) -> None:
        self.template_edit.setText(self._cfg.get("template"))
        self.api_key_edit.setText(self._cfg.get("youtube_api_key"))
        skip_mode_index = self.skip_mode_combo.findData(self._cfg.get("skip_mode"))
        if skip_mode_index >= 0:
            self.skip_mode_combo.setCurrentIndex(skip_mode_index)
        self._refresh_device_combo()

    def _refresh_device_combo(self) -> None:
        selected = self._cfg.get("audio_output_device")
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("Mặc định hệ thống", None)
        for index, name in list_output_devices():
            self.device_combo.addItem(name, index)

        if selected is not None:
            combo_index = self.device_combo.findData(selected)
            if combo_index >= 0:
                self.device_combo.setCurrentIndex(combo_index)
        self.device_combo.blockSignals(False)

    def _save_device(self, *_args) -> None:
        self._cfg.set("audio_output_device", self.device_combo.currentData())
        self._cfg.save()

    def _save_skip_mode(self, *_args) -> None:
        self._cfg.set("skip_mode", self.skip_mode_combo.currentData())
        self._cfg.save()

    def _save_template(self) -> None:
        self._cfg.set("template", self.template_edit.text())
        self._cfg.save()

    def _save_api_key(self) -> None:
        self._cfg.set("youtube_api_key", self.api_key_edit.text())
        self._cfg.save()
