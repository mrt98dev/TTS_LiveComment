from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cmtspeak.config import Config
from cmtspeak.tts.filter import parse_blocklist_file
from cmtspeak.ui.theme import PALETTE, load_icon

SAMPLE_BLOCKLIST_PATH = Path(__file__).resolve().parent.parent / "assets" / "sample_blocklist.txt"

_BLOCKLIST_MODE_LABELS: list[tuple[str, str]] = [
    ("Bỏ qua toàn bộ", "skip"),
    ("Bíp từ cấm", "bleep"),
]
_DEDUP_MODE_LABELS: list[tuple[str, str]] = [
    ("Theo nội dung", "content"),
    ("Theo người gửi", "author"),
]


class _SampleBlocklistDialog(QDialog):
    """Lists the bundled sample blocklist with a checkbox per line, letting
    the user pick which entries to import — nothing is applied until
    "Import đã chọn" is clicked, and closing/cancelling adds nothing."""

    def __init__(self, entries: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Danh sách từ cấm mẫu")
        self.resize(360, 420)
        self._selected: list[str] = []

        self.list_widget = QListWidget()
        for entry in entries:
            item = QListWidgetItem(entry)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)

        import_button = QPushButton("Import đã chọn")
        import_button.clicked.connect(self._on_import_clicked)
        cancel_button = QPushButton("Đóng")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addWidget(import_button)
        button_row.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Chọn dòng muốn thêm vào danh sách từ cấm của bạn:"))
        layout.addWidget(self.list_widget)
        layout.addLayout(button_row)

    def _on_import_clicked(self) -> None:
        self._selected = [
            self.list_widget.item(i).text()
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        ]
        self.accept()

    def selected_entries(self) -> list[str]:
        return self._selected


def _combo_with_data(labels: list[tuple[str, str]]) -> QComboBox:
    combo = QComboBox()
    for label, value in labels:
        combo.addItem(label, value)
    return combo


class FilterPage(QWidget):
    """Trang "Bộ lọc nội dung" trong sidebar — trước đây là tab của
    SettingsPanel. Mọi thay đổi (thêm/xóa/import từ cấm, đổi chế độ) được
    ghi vào Config ngay lập tức, không có nút Lưu riêng."""

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg

        self.blocklist_widget = QListWidget()
        self.blocklist_entry_edit = QLineEdit()
        self.blocklist_entry_edit.setPlaceholderText("Từ/cụm từ cần chặn")
        self.blocklist_add_button = QPushButton(load_icon("plus"), "Thêm")
        self.blocklist_remove_button = QPushButton(load_icon("trash-2"), "Xóa")
        self.blocklist_import_button = QPushButton(load_icon("folder-open"), "Import từ file...")
        self.blocklist_sample_button = QPushButton("Xem danh sách mẫu...")

        self.blocklist_mode_combo = _combo_with_data(_BLOCKLIST_MODE_LABELS)
        self.dedup_mode_combo = _combo_with_data(_DEDUP_MODE_LABELS)

        self.dedup_window_spin = QSpinBox()
        self.dedup_window_spin.setRange(1, 3600)
        self.dedup_window_spin.setSuffix(" giây")

        self._build_layout()
        self._load_from_config()

        self.blocklist_add_button.clicked.connect(self._on_add_blocklist_entry)
        self.blocklist_entry_edit.returnPressed.connect(self._on_add_blocklist_entry)
        self.blocklist_remove_button.clicked.connect(self._on_remove_blocklist_entry)
        self.blocklist_import_button.clicked.connect(self._on_import_blocklist_file)
        self.blocklist_sample_button.clicked.connect(self._on_show_sample_blocklist)
        self.blocklist_mode_combo.currentIndexChanged.connect(self._save_mode_settings)
        self.dedup_mode_combo.currentIndexChanged.connect(self._save_mode_settings)
        self.dedup_window_spin.valueChanged.connect(self._save_mode_settings)

    def _build_layout(self) -> None:
        blocklist_card = QFrame()
        blocklist_card.setProperty("class", "card")

        title_label = QLabel("Từ cấm")
        title_label.setProperty("class", "section-title")
        hint_label = QLabel("Chặn/bíp nguyên từ hoặc cụm từ, không phân biệt hoa/thường")
        hint_label.setProperty("class", "hint")

        title_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(load_icon("filter", PALETTE["text_secondary"]).pixmap(18, 18))
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch(1)

        add_row = QHBoxLayout()
        add_row.addWidget(self.blocklist_entry_edit, stretch=1)
        add_row.addWidget(self.blocklist_add_button)
        add_row.addWidget(self.blocklist_remove_button)

        import_row = QHBoxLayout()
        import_row.addWidget(self.blocklist_import_button)
        import_row.addWidget(self.blocklist_sample_button)
        import_row.addStretch(1)

        blocklist_layout = QVBoxLayout(blocklist_card)
        blocklist_layout.addLayout(title_row)
        blocklist_layout.addWidget(hint_label)
        blocklist_layout.addWidget(self.blocklist_widget)
        blocklist_layout.addLayout(add_row)
        blocklist_layout.addLayout(import_row)

        mode_card = QFrame()
        mode_card.setProperty("class", "card")
        mode_form = QFormLayout()
        mode_form.addRow("Khi khớp từ cấm:", self.blocklist_mode_combo)
        mode_form.addRow("Chặn trùng lặp:", self.dedup_mode_combo)
        mode_form.addRow("Cửa sổ thời gian trùng lặp:", self.dedup_window_spin)
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.addLayout(mode_form)

        layout = QVBoxLayout(self)
        layout.addWidget(blocklist_card)
        layout.addWidget(mode_card)
        layout.addStretch(1)

    def _blocklist_entries(self) -> list[str]:
        return [self.blocklist_widget.item(i).text() for i in range(self.blocklist_widget.count())]

    def _add_blocklist_entries(self, entries: list[str]) -> None:
        """Add entries to the in-memory list widget, skipping ones already
        present (case-sensitive exact match — good enough for a manually
        curated list; normalization only matters for matching at read time,
        not for what's shown here)."""
        existing = set(self._blocklist_entries())
        added = False
        for entry in entries:
            if entry and entry not in existing:
                self.blocklist_widget.addItem(entry)
                existing.add(entry)
                added = True
        if added:
            self._save_blocklist()

    def _save_blocklist(self) -> None:
        self._cfg.set("blocklist", self._blocklist_entries())
        self._cfg.save()

    def _save_mode_settings(self, *_args) -> None:
        self._cfg.set("blocklist_mode", self.blocklist_mode_combo.currentData())
        self._cfg.set("dedup_mode", self.dedup_mode_combo.currentData())
        self._cfg.set("dedup_window_seconds", self.dedup_window_spin.value())
        self._cfg.save()

    def _on_add_blocklist_entry(self) -> None:
        entry = self.blocklist_entry_edit.text().strip()
        if not entry:
            return
        self._add_blocklist_entries([entry])
        self.blocklist_entry_edit.clear()

    def _on_remove_blocklist_entry(self) -> None:
        item = self.blocklist_widget.currentItem()
        if item is None:
            return
        self.blocklist_widget.takeItem(self.blocklist_widget.row(item))
        self._save_blocklist()

    def _on_import_blocklist_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import từ cấm từ file", "", "Text files (*.txt)")
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi đọc file", str(exc))
            return
        self._add_blocklist_entries(parse_blocklist_file(content))

    def _on_show_sample_blocklist(self) -> None:
        try:
            content = SAMPLE_BLOCKLIST_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi đọc danh sách mẫu", str(exc))
            return
        entries = parse_blocklist_file(content)

        dialog = _SampleBlocklistDialog(entries, self)
        if dialog.exec() == QDialog.Accepted:
            self._add_blocklist_entries(dialog.selected_entries())

    def _load_from_config(self) -> None:
        self.blocklist_widget.clear()
        self._add_blocklist_entries_without_saving(self._cfg.get("blocklist"))

        blocklist_mode_index = self.blocklist_mode_combo.findData(self._cfg.get("blocklist_mode"))
        if blocklist_mode_index >= 0:
            self.blocklist_mode_combo.setCurrentIndex(blocklist_mode_index)
        dedup_mode_index = self.dedup_mode_combo.findData(self._cfg.get("dedup_mode"))
        if dedup_mode_index >= 0:
            self.dedup_mode_combo.setCurrentIndex(dedup_mode_index)
        self.dedup_window_spin.setValue(int(self._cfg.get("dedup_window_seconds")))

    def _add_blocklist_entries_without_saving(self, entries: list[str]) -> None:
        """Used only while loading from Config at startup — the values just
        came from Config, so re-saving them immediately would be a no-op
        that only costs an extra disk write."""
        existing = set(self._blocklist_entries())
        for entry in entries:
            if entry and entry not in existing:
                self.blocklist_widget.addItem(entry)
                existing.add(entry)
