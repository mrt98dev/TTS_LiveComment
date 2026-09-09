from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import numpy as np

from cmtspeak.config import Config
from cmtspeak.models import Comment

# Amplitude for the generated beep tone. Kept well below 1.0 (full scale) so
# it doesn't sound jarringly loud sitting next to normally-synthesized
# speech, which rarely peaks anywhere near full scale either.
BEEP_PEAK_AMPLITUDE = 0.3


def normalize_text(s: str) -> str:
    """Unicode NFC-normalize and lowercase a string for comparison.

    Vietnamese text can represent the same visible characters with different
    Unicode code point sequences (a precomposed character like "ệ" vs. a base
    letter followed by combining diacritic marks) — two strings that look
    identical to a person may not compare equal as raw Python strings. NFC
    normalization collapses both representations to the same form so
    comparisons behave the way a person would expect.
    """
    return unicodedata.normalize("NFC", s).lower()


def _word_pattern(word: str) -> re.Pattern[str]:
    """Compile a whole-word/phrase regex for one (already normalized) blocked
    entry. `\\b` boundaries keep this from matching a mere substring inside a
    longer, unrelated word (e.g. blocking "đm" must not match inside
    "đmx") — Python's `\\w`/`\\b` are Unicode-aware by default (re.UNICODE is
    the default for str patterns in Python 3), so this works correctly
    around Vietnamese letters with diacritics too.

    Plain `\\b` (rather than a hand-rolled `(?<!\\w)...(?!\\w)`) is
    deliberate: some entries — spam-link fragments like "zalo.me/g/" — end in
    a non-word character by design, meant to match right up against
    whatever variable ID follows (e.g. "zalo.me/g/abc123"). `\\b` there
    correctly recognizes the non-word-to-word transition as a boundary;
    a lookahead that flatly forbids any following word character would not.
    """
    escaped = re.escape(word)
    return re.compile(rf"\b{escaped}\b", re.UNICODE)


def contains_blocked_word(text: str, blocklist: list[str]) -> list[str]:
    """Return the subset of `blocklist` that appears in `text` as a whole
    word/phrase (not merely as a substring of a longer word), case-insensitive
    and Unicode-normalization-insensitive. Order follows `blocklist`, not the
    order words appear in `text`. Empty list if nothing matched."""
    normalized_text = normalize_text(text)
    found: list[str] = []
    for word in blocklist:
        normalized_word = normalize_text(word)
        if not normalized_word:
            continue
        if _word_pattern(normalized_word).search(normalized_text):
            found.append(word)
    return found


def split_around_blocked_words(text: str, blocklist: list[str]) -> list[tuple[str, bool]]:
    """Split `text` into an ordered list of `(segment, is_blocked)` pieces
    that reconstruct the original text when concatenated in order.

    Segments with `is_blocked=True` are the exact blocked word/phrase as it
    appears in `text` (original casing/form, not normalized — since these get
    replaced with a beep rather than spoken, their exact form doesn't matter
    beyond being droppable). Segments with `is_blocked=False` are the
    in-between text, verbatim. A blocked word at the very start/end of the
    text, or two blocked words adjacent to each other, never produces an
    empty non-blocked segment — empty segments are always omitted.
    """
    normalized_words = sorted(
        {normalize_text(w) for w in blocklist if normalize_text(w)},
        key=len,
        reverse=True,  # try longer phrases first so they win over shorter overlapping words
    )
    if not normalized_words:
        return [(text, False)] if text else []

    combined = "|".join(_word_pattern(w).pattern for w in normalized_words)
    pattern = re.compile(combined, re.UNICODE)

    normalized_text = normalize_text(text)

    segments: list[tuple[str, bool]] = []
    cursor = 0
    for match in pattern.finditer(normalized_text):
        start, end = match.span()
        if start > cursor:
            non_blocked = text[cursor:start]
            if non_blocked:
                segments.append((non_blocked, False))
        blocked = text[start:end]
        if blocked:
            segments.append((blocked, True))
        cursor = end

    if cursor < len(text):
        tail = text[cursor:]
        if tail:
            segments.append((tail, False))

    return segments


def generate_beep_tone(sample_rate: int, duration: float = 0.3, frequency: float = 1000.0) -> np.ndarray:
    """Generate a short sine-wave beep tone as a mono float32 numpy array,
    suitable for splicing between synthesized speech chunks. Peak amplitude
    is kept at `BEEP_PEAK_AMPLITUDE` (well below full scale) so it doesn't
    sound jarringly loud next to normal TTS output."""
    num_samples = int(round(sample_rate * duration))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)
    tone = BEEP_PEAK_AMPLITUDE * np.sin(2.0 * np.pi * frequency * t)
    return tone.astype(np.float32)


def parse_blocklist_file(text: str) -> list[str]:
    """Parse the contents of a blocklist text file (one entry per line,
    blank lines ignored) into a deduped, order-preserving list of entries.
    Shared by "Import từ file..." and the bundled sample-blocklist viewer in
    the settings UI."""
    seen: set[str] = set()
    entries: list[str] = []
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry in seen:
            continue
        seen.add(entry)
        entries.append(entry)
    return entries


@dataclass
class _HistoryEntry:
    author: str
    normalized_text: str
    ts: float


class CommentFilter:
    """Decides, per comment, whether it should be blocked (blocklist match or
    duplicate) before a `TTSWorker` synthesizes and plays it.

    Reads `blocklist`, `blocklist_mode`, `dedup_mode` and
    `dedup_window_seconds` fresh from `Config` on every call — mirroring how
    `TTSWorker._speak` already re-reads `template`/`selected_voice`/
    `audio_output_device` live, so changes made in Settings while a session
    is running take effect on the very next comment without a restart.

    Public API meant for a caller (e.g. `TTSWorker`) to use per comment:
      - `blocked_words(text) -> list[str]`
      - `should_bleep() -> bool`
      - `split_for_bleep(text) -> list[tuple[str, bool]]`
      - `is_duplicate(comment) -> bool`
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._history: list[_HistoryEntry] = []

    # -- blocklist ------------------------------------------------------

    def blocked_words(self, text: str) -> list[str]:
        """Blocked words/phrases from the current blocklist found in `text`,
        whole-word/phrase only. Empty list if none matched or the blocklist
        is empty."""
        return contains_blocked_word(text, self._cfg.get("blocklist"))

    def should_bleep(self) -> bool:
        """Whether the current `blocklist_mode` is "bleep" (speak everything
        except the blocked words, beeping over them) rather than "skip"
        (drop the whole comment)."""
        return self._cfg.get("blocklist_mode") == "bleep"

    def split_for_bleep(self, text: str) -> list[tuple[str, bool]]:
        """`split_around_blocked_words` using the current blocklist."""
        return split_around_blocked_words(text, self._cfg.get("blocklist"))

    # -- duplicate detection ---------------------------------------------

    def is_duplicate(self, comment: Comment) -> bool:
        """True if `comment` is a duplicate of something already seen within
        the current dedup window, per the current `dedup_mode`:

        - "content": duplicate if ANY author sent the same normalized text
          within `dedup_window_seconds` of `comment.ts`.
        - "author": duplicate only if the SAME author sent the same
          normalized text within the window.

        Uses `comment.ts` (not wall-clock time) for all window math, so this
        is testable with contrived timestamps and no real sleeping. If not a
        duplicate, records `comment` into the history before returning False,
        so the next identical comment within the window is caught.
        """
        window = self._cfg.get("dedup_window_seconds")
        mode = self._cfg.get("dedup_mode")

        cutoff = comment.ts - window
        self._history = [entry for entry in self._history if entry.ts >= cutoff]

        normalized = normalize_text(comment.text)
        for entry in self._history:
            if entry.normalized_text != normalized:
                continue
            if mode == "author" and entry.author != comment.author:
                continue
            return True

        self._history.append(_HistoryEntry(author=comment.author, normalized_text=normalized, ts=comment.ts))
        return False
