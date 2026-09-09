from __future__ import annotations

import pytest

from cmtspeak.connectors.base import CONNECTED, DISCONNECTED, ERROR, RECONNECTING, Connector
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.ui import connection_panel as connection_panel_module
from cmtspeak.ui.connection_panel import ConnectorRow


class _FakeConnector(Connector):
    def __init__(self, queue: CommentQueue) -> None:
        super().__init__(queue)
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture(autouse=True)
def toast_calls(monkeypatch):
    """Every test in this file runs with a fake `show_toast` so no real
    toast window pops up — tests assert on what *would* have been shown
    instead."""
    calls: list[tuple[str, str]] = []

    def fake_show_toast(text, level="error", duration_ms=4000, parent_widget=None):
        calls.append((text, level))

    monkeypatch.setattr(connection_panel_module, "show_toast", fake_show_toast)
    return calls


def _connect_row(qapp) -> tuple[ConnectorRow, _FakeConnector]:
    holder: dict[str, _FakeConnector] = {}

    def make_connector(_text: str):
        connector = _FakeConnector(CommentQueue())
        holder["connector"] = connector
        return connector

    row = ConnectorRow("placeholder", make_connector)
    row.input.setText("someuser")
    row._on_button_clicked()  # simulate clicking "Kết nối"
    return row, holder["connector"]


def test_reconnecting_status_keeps_button_as_disconnect(qapp, toast_calls):
    row, connector = _connect_row(qapp)
    row._on_status_changed(CONNECTED, "")
    assert row.button.text() == "Ngắt kết nối"

    row._on_status_changed(RECONNECTING, "Mất kết nối, thử lại sau 10s (lần 1)...")

    assert row.button.text() == "Ngắt kết nối"
    assert row.input.isEnabled() is False
    assert row.status_label.text() == "Đang kết nối lại"


def test_reconnecting_status_does_not_drop_the_connector_reference(qapp):
    """Unlike a terminal DISCONNECTED/ERROR, RECONNECTING must not reset
    _connector — the same connector instance is retrying internally, and
    clicking "Ngắt kết nối" during a backoff wait must call stop() on it to
    actually interrupt the retry loop."""
    row, connector = _connect_row(qapp)
    row._on_status_changed(RECONNECTING, "Mất kết nối, thử lại sau 10s (lần 1)...")

    row._on_button_clicked()  # user clicks "Ngắt kết nối" while reconnecting

    assert connector.stopped is True


def test_disconnected_status_resets_button_and_connector(qapp):
    row, connector = _connect_row(qapp)
    row._on_status_changed(CONNECTED, "")

    row._on_status_changed(DISCONNECTED, "")

    assert row.button.text() == "Kết nối"
    assert row.input.isEnabled() is True


def test_error_status_resets_button_and_connector(qapp):
    row, connector = _connect_row(qapp)
    row._on_status_changed(CONNECTED, "")

    row._on_status_changed(ERROR, "video không live")

    assert row.button.text() == "Kết nối"
    assert row.input.isEnabled() is True


def test_status_pill_property_tracks_status_for_qss_coloring(qapp):
    row, connector = _connect_row(qapp)
    assert row.status_label.property("status") == "disconnected"

    row._on_status_changed(CONNECTED, "")
    assert row.status_label.property("status") == "connected"

    row._on_status_changed(RECONNECTING, "Mất kết nối, thử lại sau 10s (lần 1)...")
    assert row.status_label.property("status") == "reconnecting"

    row._on_status_changed(ERROR, "video không live")
    assert row.status_label.property("status") == "error"


def test_pill_text_stays_short_regardless_of_message_length(qapp):
    """The bug being fixed: a long status/error message used to be appended
    straight into the pill's text, growing its (and the whole window's)
    minimum width. The pill must always show just the short fixed label."""
    row, connector = _connect_row(qapp)

    long_message = "Mất kết nối, thử lại sau 30s (lần 7), lý do: " + "x" * 200
    row._on_status_changed(RECONNECTING, long_message)

    assert row.status_label.text() == "Đang kết nối lại"
    assert len(row.status_label.text()) < 40


def test_full_message_is_available_as_tooltip(qapp):
    row, connector = _connect_row(qapp)

    message = "Mất kết nối, thử lại sau 10s (lần 1)..."
    row._on_status_changed(RECONNECTING, message)

    assert row.status_label.toolTip() == message


def test_toast_fires_once_on_transition_into_a_status_not_on_every_repeat(qapp, toast_calls):
    """RECONNECTING re-emits on every backoff attempt with an updated
    message — that must not spam a toast per attempt, only once when first
    entering the reconnecting state."""
    row, connector = _connect_row(qapp)

    row._on_status_changed(RECONNECTING, "Mất kết nối, thử lại sau 2s (lần 1)...")
    row._on_status_changed(RECONNECTING, "Mất kết nối, thử lại sau 5s (lần 2)...")
    row._on_status_changed(RECONNECTING, "Mất kết nối, thử lại sau 10s (lần 3)...")

    assert len(toast_calls) == 1
    assert toast_calls[0][1] == "warning"


def test_toast_fires_for_error_status(qapp, toast_calls):
    row, connector = _connect_row(qapp)

    row._on_status_changed(ERROR, "video không live")

    assert toast_calls == [("video không live", "error")]


def test_show_error_toasts_without_changing_pill_text(qapp, toast_calls):
    row, connector = _connect_row(qapp)
    pill_text_before = row.status_label.text()

    row.show_error("Vui lòng nhập thông tin trước khi kết nối")

    assert row.status_label.text() == pill_text_before
    assert toast_calls == [("Vui lòng nhập thông tin trước khi kết nối", "error")]
