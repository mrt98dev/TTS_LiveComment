import sys

from PySide6.QtWidgets import QApplication

from cmtspeak.ui.main_window import MainWindow
from cmtspeak.ui.theme import STYLESHEET


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
