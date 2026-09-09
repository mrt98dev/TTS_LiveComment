from __future__ import annotations

from cmtspeak.ui import toast as toast_module
from cmtspeak.ui.toast import show_toast


def test_show_toast_positions_at_top_right_of_screen(qapp):
    toast_module._active_toasts.clear()

    show_toast("hello", level="error", duration_ms=60_000)

    assert len(toast_module._active_toasts) == 1
    widget = toast_module._active_toasts[0]
    screen_geo = widget.screen().availableGeometry()

    assert widget.x() + widget.width() <= screen_geo.right() + 1
    assert widget.y() >= screen_geo.top()
    # Anchored to the right edge (within the configured margin).
    assert screen_geo.right() - (widget.x() + widget.width()) < 20

    widget.close()


def test_stacked_toasts_do_not_overlap(qapp):
    toast_module._active_toasts.clear()

    show_toast("first", duration_ms=60_000)
    show_toast("second", duration_ms=60_000)

    assert len(toast_module._active_toasts) == 2
    first, second = toast_module._active_toasts
    assert second.y() >= first.y() + first.height()

    first.close()
    second.close()


def test_toast_closes_itself_and_is_removed_from_active_list(qapp):
    toast_module._active_toasts.clear()

    show_toast("bye", duration_ms=60_000)
    widget = toast_module._active_toasts[0]

    widget.close()

    assert widget not in toast_module._active_toasts
