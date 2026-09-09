from __future__ import annotations

import logging
import queue
from typing import Optional

from PySide6.QtCore import QThread, Signal

from cmtspeak.audio.output import AudioOutput
from cmtspeak.config import Config
from cmtspeak.models import Comment
from cmtspeak.queue_bus import CommentQueue
from cmtspeak.tts.filter import CommentFilter, generate_beep_tone
from cmtspeak.tts.template import format_message
from cmtspeak.tts.voice_manager import VoiceManager

logger = logging.getLogger(__name__)

# Short enough that stop() takes effect quickly; long enough not to busy-loop.
QUEUE_GET_TIMEOUT = 0.5


class TTSWorker(QThread):
    """Consumes `Comment`s off the shared `CommentQueue` on its own thread,
    formats each with the current template, synthesizes speech with the
    currently selected voice, and plays it through the currently selected
    audio output device.

    `template`, `selected_voice` and `audio_output_device` are re-read from
    `Config` on every iteration, so changes made in the UI while the worker is
    running take effect on the very next comment without a restart.

    Any failure synthesizing or playing a single comment (empty text, TTS
    error, bad device, ...) is caught and reported via the `warning` signal —
    the loop keeps going, it never takes the worker down.

    `now_reading` bracket every comment taken off the queue with exactly one
    of `finished_reading` (spoken, skipped for empty text, or failed) or
    `comment_filtered` (blocklist match in "skip" mode, or a duplicate) —
    never both — so a UI tracking pending/reading/read/removed state per
    comment always sees exactly one terminal signal per comment, in order.

    A comment blocked in "bleep" mode is not filtered out: it's synthesized
    and played with the blocked word(s) replaced by a beep tone, and still
    ends with `finished_reading` like a normally spoken comment.
    """

    now_reading = Signal(Comment)
    finished_reading = Signal(Comment)
    comment_filtered = Signal(Comment, str)
    warning = Signal(str)

    def __init__(
        self,
        queue: CommentQueue,
        voice_manager: VoiceManager,
        cfg: Config,
        audio_output: AudioOutput,
        comment_filter: Optional[CommentFilter] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._queue = queue
        self._voices = voice_manager
        self._cfg = cfg
        self._audio = audio_output
        self._filter = comment_filter
        self._stop_requested = False
        self._paused = False

    def stop(self) -> None:
        """Ask the loop to exit after its current `queue.get` timeout. Does
        not touch the queue itself or any connector — comments left in the
        queue stay there for a future start()."""
        self._stop_requested = True

    def pause(self) -> None:
        """Stop consuming the queue without disconnecting anything — comments
        keep arriving and piling up, and will be read in order once
        resume() is called."""
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def skip_current(self, interrupt: bool) -> None:
        """Stop whatever comment is currently being spoken so the loop moves
        on to the next one immediately. `interrupt=False` is intentionally a
        no-op here — "skip the next queued comment without touching what's
        playing" is handled by removing it straight from the CommentQueue
        (from the UI), not through the worker at all."""
        if interrupt:
            self._audio.stop()

    def run(self) -> None:
        self._stop_requested = False
        while not self._stop_requested:
            if self._paused:
                self.msleep(int(QUEUE_GET_TIMEOUT * 1000))
                continue
            try:
                comment = self._queue.get(timeout=QUEUE_GET_TIMEOUT)
            except queue.Empty:
                continue

            self._process_one(comment)

    def _process_one(self, comment: Comment) -> None:
        """Handle exactly one dequeued comment: always emits now_reading
        then, no matter what happens in between, exactly one of
        finished_reading or comment_filtered — so a UI tracking
        pending/reading/read/removed state per comment never gets stuck with
        one stranded in "reading" forever, and never sees two terminal
        signals for the same comment."""
        self.now_reading.emit(comment)
        filtered_reason: Optional[str] = None
        try:
            filtered_reason = self._speak(comment)
        except Exception as exc:  # never let one bad comment kill the worker
            logger.exception("Failed to read comment from %s", comment.author)
            self.warning.emit(f"Không đọc được bình luận của {comment.author}: {exc}")
        finally:
            if filtered_reason is not None:
                self.comment_filtered.emit(comment, filtered_reason)
            else:
                self.finished_reading.emit(comment)

    def _speak(self, comment: Comment) -> Optional[str]:
        """Speak one comment. Returns None if it was handled as a normal
        "read" comment (spoken, bleeped, or skipped for empty text), or a
        short Vietnamese reason string if it was filtered out entirely
        (blocklist match in "skip" mode, or a duplicate) instead of being
        spoken — the caller reports that via comment_filtered rather than
        finished_reading."""
        template = self._cfg.get("template")
        voice = self._cfg.get("selected_voice")
        device = self._cfg.get("audio_output_device")

        text = format_message(comment, template)
        if not text or not text.strip():
            self.warning.emit(f"Bỏ qua bình luận rỗng của {comment.author}")
            return None

        if self._filter is not None:
            if self._filter.is_duplicate(comment):
                return "đã lọc (trùng)"

            blocked = self._filter.blocked_words(text)
            if blocked:
                if self._filter.should_bleep():
                    self._speak_with_bleep(text, voice, device)
                    return None
                return "đã lọc"

        chunks = self._voices.infer_stream(text, voice=voice)
        self._audio.play_stream(chunks, self._voices.sample_rate, device=device)
        return None

    def _speak_with_bleep(self, text: str, voice, device) -> None:
        """Synthesize `text` with each blocked word/phrase replaced by a
        beep tone instead of spoken, as one continuous playback — reuses
        AudioOutput.play_stream's own chunk-concatenation so the beep and
        surrounding speech play back gaplessly like a normal comment."""
        sample_rate = self._voices.sample_rate
        segments = self._filter.split_for_bleep(text)

        def chunks():
            for segment, is_blocked in segments:
                if is_blocked:
                    yield generate_beep_tone(sample_rate)
                    continue
                if not segment.strip():
                    continue
                yield from self._voices.infer_stream(segment, voice=voice)

        self._audio.play_stream(chunks(), sample_rate, device=device)
