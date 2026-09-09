from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from cmtspeak.audio.output import AudioOutput
from cmtspeak.config import Config
from cmtspeak.tts.voice_manager import VoiceManager
from cmtspeak.ui.theme import PALETTE, load_icon

DEFAULT_DEMO_TEXT = "Xin chào, đây là giọng đọc demo."


class _VoiceListLoader(QThread):
    """Loads the voice list on a background thread. Listing voices is the
    first thing that touches VoiceManager.engine, which constructs the real
    vieneu.Vieneu() model (and may download it on first run) — doing that on
    the Qt main thread would freeze the whole window at startup."""

    loaded = Signal(list)

    def __init__(self, voice_manager: VoiceManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._voices = voice_manager

    def run(self) -> None:
        try:
            voices = self._voices.list_voices()
        except Exception:  # noqa: BLE001 - report an empty list rather than crash
            voices = []
        self.loaded.emit(voices)


class _VoiceDemoWorker(QThread):
    """Synthesizes and plays one demo sentence with a given voice, on a
    background thread so previewing a voice never freezes the window."""

    failed = Signal(str)
    finished_playing = Signal()

    def __init__(
        self,
        voice_manager: VoiceManager,
        audio_output: AudioOutput,
        voice_id: str,
        device,
        text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._voices = voice_manager
        self._audio = audio_output
        self._voice_id = voice_id
        self._device = device
        self._text = text

    def run(self) -> None:
        try:
            chunks = self._voices.infer_stream(self._text, voice=self._voice_id)
            self._audio.play_stream(chunks, self._voices.sample_rate, device=self._device)
        except Exception as exc:  # noqa: BLE001 - report, never crash the thread
            self.failed.emit(str(exc))
        else:
            self.finished_playing.emit()


class _EditCloneVoiceDialog(QDialog):
    """Rename a cloned voice and/or replace its reference audio."""

    def __init__(self, current_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sửa giọng clone")
        self.new_wav_path: str | None = None

        self.name_edit = QLineEdit(current_name)
        self.wav_label = QLabel("Không đổi audio mẫu")
        pick_button = QPushButton("Chọn audio mẫu mới...")
        pick_button.clicked.connect(self._pick_file)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        wav_row = QHBoxLayout()
        wav_row.addWidget(self.wav_label, stretch=1)
        wav_row.addWidget(pick_button)

        form = QFormLayout()
        form.addRow("Tên:", self.name_edit)
        form.addRow("Audio mẫu:", wav_row)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file audio mẫu mới (3-8 giây)", "", "Audio files (*.wav *.mp3 *.flac)"
        )
        if path:
            self.new_wav_path = path
            self.wav_label.setText(Path(path).name)

    def result_values(self) -> tuple[str, str | None]:
        return self.name_edit.text().strip(), self.new_wav_path


class _VoiceItemDelegate(QStyledItemDelegate):
    """Draws a small "Clone" pill on the right of a voice row when the item
    is a cloned voice, instead of the old text suffix "  (Clone)"."""

    _MARGIN = 8
    _PADDING = 6

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:  # noqa: N802
        super().paint(painter, option, index)
        if not bool(index.data(Qt.UserRole + 1)):
            return

        painter.save()
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)

        text = "Clone"
        metrics = painter.fontMetrics()
        badge_width = metrics.horizontalAdvance(text) + 2 * self._PADDING
        badge_height = metrics.height() + 4
        badge_rect = QRect(
            option.rect.right() - self._MARGIN - badge_width,
            option.rect.y() + (option.rect.height() - badge_height) // 2,
            badge_width,
            badge_height,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PALETTE["accent"]))
        painter.drawRoundedRect(badge_rect, badge_height // 2, badge_height // 2)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge_rect, Qt.AlignCenter, text)
        painter.restore()


class VoicesPage(QWidget):
    """Trang "Giọng đọc" trong sidebar — trước đây là tab của SettingsPanel.
    Chọn giọng lưu vào Config ngay khi người dùng đổi lựa chọn (không có nút
    Lưu riêng); thêm/sửa/xóa giọng clone vẫn áp dụng ngay như cũ, vì mỗi thao
    tác là một hành động một lần trực tiếp trên VoiceManager."""

    def __init__(
        self,
        cfg: Config,
        voice_manager: VoiceManager,
        audio_output: AudioOutput,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._voices = voice_manager
        self._audio = audio_output
        self._demo_worker: _VoiceDemoWorker | None = None

        self.voice_list = QListWidget()
        self.voice_list.setItemDelegate(_VoiceItemDelegate(self.voice_list))
        self.demo_text_edit = QLineEdit(DEFAULT_DEMO_TEXT)
        self.demo_button = QPushButton(load_icon("volume-2"), "Nghe demo")
        self.edit_clone_button = QPushButton(load_icon("pencil"), "Sửa")
        self.remove_clone_button = QPushButton(load_icon("trash-2"), "Xóa")

        self.clone_name_edit = QLineEdit()
        self.clone_name_edit.setPlaceholderText("Tên giọng mới")
        self.clone_add_button = QPushButton(load_icon("plus"), "Thêm giọng từ file mẫu...")

        self._build_layout()

        self.voice_list.setEnabled(False)
        self.demo_button.setEnabled(False)
        self.edit_clone_button.setEnabled(False)
        self.remove_clone_button.setEnabled(False)
        self.voice_list.addItem("Đang tải danh sách giọng...")

        self._voice_loader = _VoiceListLoader(self._voices, self)
        self._voice_loader.loaded.connect(self._populate_voice_list)
        self._voice_loader.start()

        self.voice_list.currentItemChanged.connect(self._on_voice_selection_changed)
        self.clone_add_button.clicked.connect(self._on_add_clone_voice)
        self.edit_clone_button.clicked.connect(self._on_edit_clone_voice)
        self.remove_clone_button.clicked.connect(self._on_remove_clone_voice)
        self.demo_button.clicked.connect(self._on_demo_clicked)

    def _build_layout(self) -> None:
        card = QFrame()
        card.setProperty("class", "card")

        voice_buttons_row = QHBoxLayout()
        voice_buttons_row.addWidget(self.demo_button)
        voice_buttons_row.addWidget(self.edit_clone_button)
        voice_buttons_row.addWidget(self.remove_clone_button)
        voice_buttons_row.addStretch(1)

        clone_add_row = QHBoxLayout()
        clone_add_row.addWidget(self.clone_name_edit)
        clone_add_row.addWidget(self.clone_add_button)

        demo_form = QFormLayout()
        demo_form.addRow("Câu demo:", self.demo_text_edit)

        title_label = QLabel("Giọng đọc")
        title_label.setProperty("class", "section-title")

        title_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(load_icon("mic-2", PALETTE["text_secondary"]).pixmap(18, 18))
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch(1)

        card_layout = QVBoxLayout(card)
        card_layout.addLayout(title_row)
        card_layout.addWidget(self.voice_list)
        card_layout.addLayout(voice_buttons_row)
        card_layout.addLayout(demo_form)
        card_layout.addWidget(QLabel("<b>Thêm giọng clone mới</b>"))
        card_layout.addLayout(clone_add_row)

        layout = QVBoxLayout(self)
        layout.addWidget(card)
        layout.addStretch(1)

    # -- voices -------------------------------------------------------

    def _populate_voice_list(self, voices: list[tuple[str, str]]) -> None:
        selected = self._cfg.get("selected_voice")
        self.voice_list.blockSignals(True)
        self.voice_list.clear()

        selected_row = -1
        for label, voice_id in voices:
            is_clone = self._voices.is_clone_voice(voice_id)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, voice_id)
            item.setData(Qt.UserRole + 1, is_clone)
            self.voice_list.addItem(item)
            if voice_id == selected:
                selected_row = self.voice_list.count() - 1

        if selected_row >= 0:
            self.voice_list.setCurrentRow(selected_row)
        self.voice_list.blockSignals(False)

        self.voice_list.setEnabled(True)
        self._update_voice_action_buttons()

    def _refresh_voice_list(self) -> None:
        """Reload voices synchronously — safe to call after add/edit/remove
        clone voice, since those already forced the engine to load."""
        self._populate_voice_list(self._voices.list_voices())

    def _current_voice_item(self) -> QListWidgetItem | None:
        return self.voice_list.currentItem()

    def _update_voice_action_buttons(self) -> None:
        item = self._current_voice_item()
        has_selection = item is not None
        is_clone = bool(item.data(Qt.UserRole + 1)) if item is not None else False
        self.demo_button.setEnabled(has_selection)
        self.edit_clone_button.setEnabled(is_clone)
        self.remove_clone_button.setEnabled(is_clone)

    def _on_voice_selection_changed(self, *_args) -> None:
        self._update_voice_action_buttons()
        item = self._current_voice_item()
        if item is None:
            return
        self._cfg.set("selected_voice", item.data(Qt.UserRole))
        self._cfg.save()

    def _on_add_clone_voice(self) -> None:
        name = self.clone_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Thiếu tên", "Vui lòng nhập tên cho giọng mới.")
            return

        wav_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file audio mẫu (3-8 giây)", "", "Audio files (*.wav *.mp3 *.flac)"
        )
        if not wav_path:
            return

        try:
            self._voices.add_clone_voice(name, wav_path)
        except Exception as exc:  # noqa: BLE001 - surface any cloning failure to the user
            QMessageBox.critical(self, "Lỗi tạo giọng clone", str(exc))
            return

        self.clone_name_edit.clear()
        self._refresh_voice_list()

    def _on_edit_clone_voice(self) -> None:
        item = self._current_voice_item()
        if item is None or not item.data(Qt.UserRole + 1):
            return
        old_name = item.data(Qt.UserRole)

        dialog = _EditCloneVoiceDialog(old_name, self)
        if dialog.exec() != QDialog.Accepted:
            return
        new_name, new_wav_path = dialog.result_values()
        if not new_name:
            QMessageBox.warning(self, "Thiếu tên", "Tên giọng không được để trống.")
            return

        try:
            self._voices.update_clone_voice(old_name, new_name, new_wav_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Lỗi sửa giọng", str(exc))
            return
        self._refresh_voice_list()

    def _on_remove_clone_voice(self) -> None:
        item = self._current_voice_item()
        if item is None or not item.data(Qt.UserRole + 1):
            return
        name = item.data(Qt.UserRole)
        try:
            self._voices.remove_clone_voice(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Lỗi xóa giọng", str(exc))
            return
        self._refresh_voice_list()

    def _on_demo_clicked(self) -> None:
        item = self._current_voice_item()
        if item is None:
            return
        voice_id = item.data(Qt.UserRole)
        if not voice_id:
            return
        if self._demo_worker is not None and self._demo_worker.isRunning():
            return

        text = self.demo_text_edit.text().strip() or DEFAULT_DEMO_TEXT

        self.demo_button.setEnabled(False)
        self.demo_button.setText("Đang phát...")

        device = self._cfg.get("audio_output_device")
        self._demo_worker = _VoiceDemoWorker(self._voices, self._audio, voice_id, device, text, self)
        self._demo_worker.finished_playing.connect(self._on_demo_finished)
        self._demo_worker.failed.connect(self._on_demo_failed)
        self._demo_worker.start()

    def _on_demo_finished(self) -> None:
        self.demo_button.setText("Nghe demo")
        self._update_voice_action_buttons()

    def _on_demo_failed(self, message: str) -> None:
        self.demo_button.setText("Nghe demo")
        self._update_voice_action_buttons()
        QMessageBox.warning(self, "Không phát được demo", message)

    # -- shutdown ---------------------------------------------------------

    def shutdown(self) -> None:
        """Give the background voice-list loader a bounded chance to finish
        before the window closes — a QThread destroyed while still running
        aborts the whole process. With the model already cached (the normal
        case after the first run) this comfortably finishes in time; on a
        genuine first run still downloading the model, closing the app this
        early isn't a supported scenario."""
        if self._voice_loader.isRunning():
            self._voice_loader.wait(5000)
        if self._demo_worker is not None and self._demo_worker.isRunning():
            self._demo_worker.wait(5000)
