from __future__ import annotations

from cmtspeak.models import Comment
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.ui.log_panel import ReadStatus, _PLATFORM_ROLE, _STATUS_ROLE, LogPanel


def _comment(author: str, text: str) -> Comment:
    return Comment(platform="mock", author=author, text=text, ts=0.0)


def test_new_comment_starts_pending(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)

    queue.put(_comment("An", "hello"))

    assert panel.list_widget.count() == 1
    item = panel.list_widget.item(0)
    assert item.data(_STATUS_ROLE) == ReadStatus.PENDING
    assert item.data(_PLATFORM_ROLE) == "mock"
    assert "An" in item.text() and "hello" in item.text()


def test_now_reading_marks_oldest_pending_as_reading(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1, c2 = _comment("An", "first"), _comment("Bi", "second")
    queue.put(c1)
    queue.put(c2)

    panel.set_now_reading(c1)

    item0, item1 = panel.list_widget.item(0), panel.list_widget.item(1)
    assert item0.data(_STATUS_ROLE) == ReadStatus.READING
    assert item1.data(_STATUS_ROLE) == ReadStatus.PENDING


def test_finished_reading_marks_it_read_and_advances_to_next(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1, c2 = _comment("An", "first"), _comment("Bi", "second")
    queue.put(c1)
    queue.put(c2)

    panel.set_now_reading(c1)
    panel.set_finished_reading(c1)

    item0 = panel.list_widget.item(0)
    assert item0.data(_STATUS_ROLE) == ReadStatus.READ

    panel.set_now_reading(c2)
    item1 = panel.list_widget.item(1)
    assert item1.data(_STATUS_ROLE) == ReadStatus.READING


def test_full_lifecycle_order_matches_arrival_order(qapp):
    """Mirrors the real worker contract: now_reading then finished_reading,
    once each, strictly in the order comments arrived."""
    queue = CommentQueue()
    panel = LogPanel(queue)
    comments = [_comment(f"user{i}", f"text{i}") for i in range(3)]
    for c in comments:
        queue.put(c)

    for c in comments:
        panel.set_now_reading(c)
        panel.set_finished_reading(c)

    for i in range(3):
        assert panel.list_widget.item(i).data(_STATUS_ROLE) == ReadStatus.READ


def test_mark_removed_marks_pending_items_with_reason(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1, c2, c3 = _comment("An", "first"), _comment("Bi", "second"), _comment("Cy", "third")
    queue.put(c1)
    queue.put(c2)
    queue.put(c3)

    panel.mark_removed([c1, c2], reason="đã xóa")

    item0, item1, item2 = (panel.list_widget.item(i) for i in range(3))
    assert item0.data(_STATUS_ROLE) == ReadStatus.REMOVED
    assert "đã xóa" in item0.text()
    assert item1.data(_STATUS_ROLE) == ReadStatus.REMOVED
    assert "đã xóa" in item1.text()
    assert item2.data(_STATUS_ROLE) == ReadStatus.PENDING


def test_mark_removed_distinguishes_reason_text(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1 = _comment("An", "first")
    queue.put(c1)

    panel.mark_removed([c1], reason="đã bỏ qua")

    item0 = panel.list_widget.item(0)
    assert "đã bỏ qua" in item0.text()
    assert "đã xóa" not in item0.text()


def test_mark_removed_does_not_touch_reading_item(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1, c2 = _comment("An", "first"), _comment("Bi", "second")
    queue.put(c1)
    queue.put(c2)

    panel.set_now_reading(c1)  # c1's row is now READING, still in _pending_items
    panel.mark_removed([c2], reason="đã xóa")  # c2 is what queue.clear() would return

    item0, item1 = panel.list_widget.item(0), panel.list_widget.item(1)
    assert item0.data(_STATUS_ROLE) == ReadStatus.READING
    assert item1.data(_STATUS_ROLE) == ReadStatus.REMOVED

    # the reading item must still be trackable by a later finished_reading
    panel.set_finished_reading(c1)
    assert item0.data(_STATUS_ROLE) == ReadStatus.READ


def test_mark_removed_does_not_touch_already_read_item(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1, c2 = _comment("An", "first"), _comment("Bi", "second")
    queue.put(c1)
    queue.put(c2)

    panel.set_now_reading(c1)
    panel.set_finished_reading(c1)  # c1's row is now READ, no longer in _pending_items
    panel.mark_removed([c2], reason="đã xóa")

    item0, item1 = panel.list_widget.item(0), panel.list_widget.item(1)
    assert item0.data(_STATUS_ROLE) == ReadStatus.READ
    assert item1.data(_STATUS_ROLE) == ReadStatus.REMOVED


def test_set_filtered_marks_the_reading_item_removed_with_reason(qapp):
    """Mirrors TTSWorker's contract: a filtered comment was already marked
    READING by set_now_reading before the worker decided not to speak it —
    set_filtered must replace that with a distinct removed state instead of
    the normal "✓ đã đọc", and must advance tracking the same way
    set_finished_reading does."""
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1, c2 = _comment("An", "spam"), _comment("Bi", "second")
    queue.put(c1)
    queue.put(c2)

    panel.set_now_reading(c1)
    panel.set_filtered(c1, "đã lọc")

    item0 = panel.list_widget.item(0)
    assert item0.data(_STATUS_ROLE) == ReadStatus.REMOVED
    assert "đã lọc" in item0.text()

    # tracking correctly advanced to the next comment
    panel.set_now_reading(c2)
    item1 = panel.list_widget.item(1)
    assert item1.data(_STATUS_ROLE) == ReadStatus.READING


def test_set_filtered_distinguishes_duplicate_reason(qapp):
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1 = _comment("An", "spam")
    queue.put(c1)

    panel.set_now_reading(c1)
    panel.set_filtered(c1, "đã lọc (trùng)")

    item0 = panel.list_widget.item(0)
    assert "đã lọc (trùng)" in item0.text()


def test_finished_reading_without_prior_now_reading_is_safe(qapp):
    """A comment skipped so fast that only finished_reading is observed
    (e.g. UI catches up late) must not crash or misalign later items."""
    queue = CommentQueue()
    panel = LogPanel(queue)
    c1, c2 = _comment("An", "first"), _comment("Bi", "second")
    queue.put(c1)
    queue.put(c2)

    panel.set_finished_reading(c1)  # no set_now_reading beforehand
    assert panel.list_widget.item(0).data(_STATUS_ROLE) == ReadStatus.READ

    panel.set_now_reading(c2)
    assert panel.list_widget.item(1).data(_STATUS_ROLE) == ReadStatus.READING
