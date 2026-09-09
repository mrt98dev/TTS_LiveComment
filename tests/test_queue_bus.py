from __future__ import annotations

import threading
import time

from cmtspeak.models import Comment
from cmtspeak.queue_bus import CommentQueue


def _comment(i: int) -> Comment:
    return Comment(platform="mock", author=f"user{i}", text=f"comment {i}", ts=float(i))


def test_fifo_order_single_thread():
    q = CommentQueue()
    for i in range(5):
        q.put(_comment(i))

    assert q.size == 5
    for i in range(5):
        assert q.get(timeout=1).text == f"comment {i}"
    assert q.size == 0


def test_fifo_order_preserved_across_threads():
    q = CommentQueue()
    received: list[Comment] = []

    def producer(start: int, count: int) -> None:
        for i in range(start, start + count):
            q.put(_comment(i))
            time.sleep(0.001)

    # Two producers writing disjoint, monotonically increasing ranges: each
    # producer's own comments must come out in its own order even though the
    # two threads interleave.
    t1 = threading.Thread(target=producer, args=(0, 10))
    t2 = threading.Thread(target=producer, args=(100, 10))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert q.size == 20
    for _ in range(20):
        received.append(q.get(timeout=1))

    low = [c for c in received if int(c.ts) < 100]
    high = [c for c in received if int(c.ts) >= 100]
    assert [int(c.ts) for c in low] == list(range(0, 10))
    assert [int(c.ts) for c in high] == list(range(100, 110))


def test_comment_received_signal_emitted():
    q = CommentQueue()
    seen: list[Comment] = []
    q.comment_received.connect(seen.append)

    c = _comment(1)
    q.put(c)

    assert seen == [c]


def test_clear_drains_all_waiting_in_fifo_order():
    q = CommentQueue()
    for i in range(5):
        q.put(_comment(i))

    drained = q.clear()

    assert [c.text for c in drained] == [f"comment {i}" for i in range(5)]
    assert q.size == 0


def test_clear_does_not_touch_an_item_already_taken_by_get():
    q = CommentQueue()
    for i in range(3):
        q.put(_comment(i))

    taken = q.get(timeout=1)  # simulates a worker already holding comment 0
    drained = q.clear()

    assert taken.text == "comment 0"
    assert [c.text for c in drained] == ["comment 1", "comment 2"]
    assert q.size == 0


def test_clear_on_empty_queue_returns_empty_list():
    q = CommentQueue()

    assert q.clear() == []
    assert q.size == 0


def test_pop_next_returns_oldest_waiting_item():
    q = CommentQueue()
    for i in range(3):
        q.put(_comment(i))

    popped = q.pop_next()

    assert popped is not None
    assert popped.text == "comment 0"
    assert q.size == 2


def test_pop_next_on_empty_queue_returns_none():
    q = CommentQueue()

    assert q.pop_next() is None
    assert q.size == 0


def test_pop_next_does_not_disturb_items_after_it():
    q = CommentQueue()
    for i in range(3):
        q.put(_comment(i))

    q.pop_next()

    assert q.get(timeout=1).text == "comment 1"
    assert q.get(timeout=1).text == "comment 2"


def test_pop_next_does_not_touch_an_item_already_taken_by_get():
    q = CommentQueue()
    for i in range(3):
        q.put(_comment(i))

    taken = q.get(timeout=1)  # simulates a worker already holding comment 0
    popped = q.pop_next()

    assert taken.text == "comment 0"
    assert popped is not None
    assert popped.text == "comment 1"
    assert q.size == 1
