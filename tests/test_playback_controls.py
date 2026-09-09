from __future__ import annotations

import pathlib
import tempfile

from cmtspeak.config import Config
from cmtspeak.models import Comment
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.ui.log_panel import LogPanel
from cmtspeak.ui.playback_controls import PlaybackControls


class _FakeWorker:
    def __init__(self) -> None:
        self.paused = False
        self.resumed = False
        self.skipped_interrupt: bool | None = None

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.resumed = True

    def skip_current(self, interrupt: bool) -> None:
        self.skipped_interrupt = interrupt


def _make_controls(qapp) -> tuple[PlaybackControls, CommentQueue, Config]:
    cfg = Config(pathlib.Path(tempfile.mktemp()))
    queue = CommentQueue()
    log_panel = LogPanel(queue)
    controls = PlaybackControls(_FakeWorker(), cfg, queue, log_panel)
    return controls, queue, cfg


def test_queue_size_badge_reflects_current_queue_size(qapp):
    controls, queue, _cfg = _make_controls(qapp)
    assert controls.queue_size_badge.text() == "0 đang chờ"

    queue.put(Comment(platform="mock", author="a", text="hi", ts=0.0))
    queue.put(Comment(platform="mock", author="b", text="yo", ts=0.0))
    controls._update_queue_size_badge()

    assert controls.queue_size_badge.text() == "2 đang chờ"


def test_skip_next_only_pops_oldest_without_touching_worker(qapp):
    controls, queue, cfg = _make_controls(qapp)
    cfg.set("skip_mode", "next_only")
    queue.put(Comment(platform="mock", author="a", text="hi", ts=0.0))

    controls._on_skip_clicked()

    assert queue.size == 0
    assert controls._worker.skipped_interrupt is None


def test_skip_interrupt_mode_calls_worker(qapp):
    controls, _queue, cfg = _make_controls(qapp)
    cfg.set("skip_mode", "interrupt")

    controls._on_skip_clicked()

    assert controls._worker.skipped_interrupt is True
