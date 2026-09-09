from __future__ import annotations

import pytest

from cmtspeak.config import Config
from cmtspeak.models import Comment
from cmtspeak.tts.filter import CommentFilter
from cmtspeak.tts.worker import TTSWorker


class FakeVoiceManager:
    sample_rate = 48_000

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def infer_stream(self, text: str, voice=None):
        self.calls.append((text, voice))
        yield b"chunk"


class BrokenVoiceManager:
    """Raises on every inference — used to test the finished_reading
    contract when _speak fails partway through."""

    sample_rate = 48_000

    def infer_stream(self, text: str, voice=None):
        raise RuntimeError("boom")


class FakeAudioOutput:
    def __init__(self) -> None:
        self.played: list[tuple[list, int, object]] = []

    def play_stream(self, chunks, sample_rate, device=None):
        self.played.append((list(chunks), sample_rate, device))


@pytest.fixture
def cfg(tmp_path):
    c = Config(path=tmp_path / "config.json")
    c.set("template", "{name}: {content}")
    c.set("selected_voice", "voice_a")
    c.set("audio_output_device", None)
    return c


def _worker(cfg, voice_manager=None, comment_filter=None) -> tuple[TTSWorker, FakeVoiceManager, FakeAudioOutput]:
    voices = voice_manager if voice_manager is not None else FakeVoiceManager()
    audio = FakeAudioOutput()
    worker = TTSWorker(
        queue=None, voice_manager=voices, cfg=cfg, audio_output=audio, comment_filter=comment_filter
    )
    return worker, voices, audio


def test_speak_skips_comment_that_formats_to_empty_text(cfg):
    cfg.set("template", "{content}")
    worker, voices, audio = _worker(cfg)

    warnings: list[str] = []
    worker.warning.connect(warnings.append)

    comment = Comment(platform="mock", author="An", text="   ", ts=0.0)
    worker._speak(comment)

    assert voices.calls == []
    assert audio.played == []
    assert len(warnings) == 1


def test_speak_formats_synthesizes_and_plays(cfg):
    worker, voices, audio = _worker(cfg)

    comment = Comment(platform="mock", author="An", text="Hello", ts=0.0)
    worker._speak(comment)

    assert voices.calls == [("An: Hello", "voice_a")]
    assert len(audio.played) == 1
    played_chunks, sample_rate, device = audio.played[0]
    assert played_chunks == [b"chunk"]
    assert sample_rate == 48_000
    assert device is None


def test_speak_rereads_config_on_every_call(cfg):
    worker, voices, audio = _worker(cfg)

    worker._speak(Comment(platform="mock", author="An", text="Hello", ts=0.0))
    cfg.set("selected_voice", "voice_b")
    cfg.set("template", "{content}")
    worker._speak(Comment(platform="mock", author="Bi", text="World", ts=1.0))

    assert voices.calls == [("An: Hello", "voice_a"), ("World", "voice_b")]


def test_process_one_emits_now_reading_then_finished_reading(cfg):
    worker, voices, audio = _worker(cfg)

    events: list[tuple[str, Comment]] = []
    worker.now_reading.connect(lambda c: events.append(("now_reading", c)))
    worker.finished_reading.connect(lambda c: events.append(("finished_reading", c)))

    comment = Comment(platform="mock", author="An", text="Hello", ts=0.0)
    worker._process_one(comment)

    assert events == [("now_reading", comment), ("finished_reading", comment)]


def test_process_one_emits_finished_reading_even_when_skipped(cfg):
    """A comment that formats to empty text never reaches _speak's TTS call,
    but a UI tracking pending/reading/read state per comment must still see
    it move out of "reading" — otherwise it's stuck there forever."""
    cfg.set("template", "{content}")
    worker, voices, audio = _worker(cfg)

    events: list[str] = []
    worker.now_reading.connect(lambda c: events.append("now_reading"))
    worker.finished_reading.connect(lambda c: events.append("finished_reading"))

    worker._process_one(Comment(platform="mock", author="An", text="   ", ts=0.0))

    assert events == ["now_reading", "finished_reading"]


def test_process_one_emits_finished_reading_even_when_speak_raises(cfg):
    worker, voices, audio = _worker(cfg, voice_manager=BrokenVoiceManager())

    events: list[str] = []
    warnings: list[str] = []
    worker.now_reading.connect(lambda c: events.append("now_reading"))
    worker.finished_reading.connect(lambda c: events.append("finished_reading"))
    worker.warning.connect(warnings.append)

    worker._process_one(Comment(platform="mock", author="An", text="Hello", ts=0.0))

    assert events == ["now_reading", "finished_reading"]
    assert len(warnings) == 1


def test_speak_returns_none_and_plays_when_no_filter_configured(cfg):
    worker, voices, audio = _worker(cfg, comment_filter=None)

    result = worker._speak(Comment(platform="mock", author="An", text="Hello", ts=0.0))

    assert result is None
    assert len(audio.played) == 1


def test_speak_filters_duplicate_without_synthesizing(cfg):
    cfg.set("dedup_mode", "content")
    cfg.set("dedup_window_seconds", 10)
    comment_filter = CommentFilter(cfg)
    worker, voices, audio = _worker(cfg, comment_filter=comment_filter)

    first = Comment(platform="mock", author="An", text="Hello", ts=0.0)
    second = Comment(platform="mock", author="Bi", text="Hello", ts=1.0)

    result1 = worker._speak(first)
    result2 = worker._speak(second)

    assert result1 is None
    assert result2 == "đã lọc (trùng)"
    assert len(voices.calls) == 1  # second comment never reached synthesis
    assert len(audio.played) == 1


def test_speak_filters_blocked_word_in_skip_mode(cfg):
    cfg.set("template", "{content}")
    cfg.set("blocklist", ["xấu"])
    cfg.set("blocklist_mode", "skip")
    comment_filter = CommentFilter(cfg)
    worker, voices, audio = _worker(cfg, comment_filter=comment_filter)

    result = worker._speak(Comment(platform="mock", author="An", text="đồ xấu tính", ts=0.0))

    assert result == "đã lọc"
    assert voices.calls == []
    assert audio.played == []


def test_speak_bleeps_blocked_word_instead_of_skipping(cfg):
    cfg.set("template", "{content}")
    cfg.set("blocklist", ["xấu"])
    cfg.set("blocklist_mode", "bleep")
    comment_filter = CommentFilter(cfg)
    worker, voices, audio = _worker(cfg, comment_filter=comment_filter)

    result = worker._speak(Comment(platform="mock", author="An", text="đồ xấu tính", ts=0.0))

    assert result is None  # bleeped comments count as normally handled, not filtered
    # Only the non-blocked segments go through TTS; the blocked word doesn't.
    assert all("xấu" not in text for text, _voice in voices.calls)
    assert len(audio.played) == 1
    played_chunks, _sample_rate, _device = audio.played[0]
    assert len(played_chunks) > 1  # speech chunk(s) + at least one beep tone


def test_process_one_emits_comment_filtered_instead_of_finished_reading(cfg):
    cfg.set("template", "{content}")
    cfg.set("blocklist", ["xấu"])
    cfg.set("blocklist_mode", "skip")
    comment_filter = CommentFilter(cfg)
    worker, voices, audio = _worker(cfg, comment_filter=comment_filter)

    events: list[tuple[str, object]] = []
    worker.now_reading.connect(lambda c: events.append(("now_reading", c)))
    worker.finished_reading.connect(lambda c: events.append(("finished_reading", c)))
    worker.comment_filtered.connect(lambda c, reason: events.append(("comment_filtered", reason)))

    comment = Comment(platform="mock", author="An", text="đồ xấu tính", ts=0.0)
    worker._process_one(comment)

    assert events == [("now_reading", comment), ("comment_filtered", "đã lọc")]
