from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication for the whole test session — required before
    constructing any QWidget (QListWidget, QLineEdit, ...), even headless."""
    app = QApplication.instance() or QApplication([])
    yield app
