from __future__ import annotations

import unicodedata

import numpy as np
import pytest

from cmtspeak.config import Config
from cmtspeak.models import Comment
from cmtspeak.tts.filter import (
    CommentFilter,
    contains_blocked_word,
    generate_beep_tone,
    normalize_text,
    parse_blocklist_file,
    split_around_blocked_words,
)


@pytest.fixture
def cfg(tmp_path):
    return Config(path=tmp_path / "config.json")


# -- normalize_text / contains_blocked_word --------------------------------


def test_whole_word_match_does_not_match_substring_inside_longer_word():
    assert contains_blocked_word("thằng đmx này", ["đm"]) == []
    assert contains_blocked_word("mày đm à", ["đm"]) == ["đm"]


def test_case_insensitive_match():
    assert contains_blocked_word("Đây là ĐM đó", ["đm"]) == ["đm"]
    assert contains_blocked_word("this is SPAM here", ["spam"]) == ["spam"]


def test_no_match_returns_empty_list():
    assert contains_blocked_word("một câu bình thường", ["đm", "spam"]) == []


def test_unicode_nfc_nfd_variants_of_same_word_still_match():
    # "đéo" written normally (NFC-composed) vs. decomposed into base letters
    # + combining diacritic marks (NFD) look identical to a person but are
    # different Python strings until normalized.
    nfc_word = "đéo"
    nfd_word = unicodedata.normalize("NFD", nfc_word)
    assert nfc_word != nfd_word  # sanity check they really are different code points

    text_with_nfd = f"mày {nfd_word} à"
    assert contains_blocked_word(text_with_nfd, [nfc_word]) == [nfc_word]

    text_with_nfc = f"mày {nfc_word} à"
    assert contains_blocked_word(text_with_nfc, [nfd_word]) == [nfd_word]


def test_multi_word_phrase_matches_as_a_phrase():
    assert contains_blocked_word("liên hệ zalo.me/g/abc123 nhé", ["zalo.me/g/"]) == ["zalo.me/g/"]
    assert contains_blocked_word("đăng ký kênh spam link ngay", ["spam link"]) == ["spam link"]
    assert contains_blocked_word("đây là link spam thôi", ["spam link"]) == []


def test_returns_words_in_blocklist_order_not_text_order():
    assert contains_blocked_word("foo và bar cùng xuất hiện", ["bar", "foo"]) == ["bar", "foo"]


def test_normalize_text_lowercases_and_nfc_normalizes():
    nfd = unicodedata.normalize("NFD", "VIỆT NAM")
    assert normalize_text(nfd) == normalize_text("việt nam")


# -- split_around_blocked_words --------------------------------------------


def _reconstruct(segments: list[tuple[str, bool]]) -> str:
    return "".join(seg for seg, _blocked in segments)


def test_split_no_blocked_words_returns_whole_text_as_one_segment():
    text = "một câu bình thường không có gì"
    segments = split_around_blocked_words(text, ["đm", "spam"])
    assert segments == [(text, False)]


def test_split_blocked_word_in_the_middle():
    segments = split_around_blocked_words("mày đm à", ["đm"])
    assert segments == [("mày ", False), ("đm", True), (" à", False)]
    assert _reconstruct(segments) == "mày đm à"


def test_split_blocked_word_at_start():
    segments = split_around_blocked_words("đm mày à", ["đm"])
    assert segments[0] == ("đm", True)
    assert all(seg for seg, _ in segments)  # no empty segments
    assert _reconstruct(segments) == "đm mày à"


def test_split_blocked_word_at_end():
    segments = split_around_blocked_words("mày à đm", ["đm"])
    assert segments[-1] == ("đm", True)
    assert all(seg for seg, _ in segments)
    assert _reconstruct(segments) == "mày à đm"


def test_split_two_adjacent_blocked_words_no_empty_segment_between():
    segments = split_around_blocked_words("đm ngu ơi", ["đm", "ngu"])
    # No ("", False) squeezed between the two blocked matches.
    assert ("", False) not in segments
    blocked_segments = [seg for seg, is_blocked in segments if is_blocked]
    assert blocked_segments == ["đm", "ngu"]
    assert _reconstruct(segments) == "đm ngu ơi"


def test_split_multiple_non_adjacent_blocked_words():
    text = "đm mày spam quá đm"
    segments = split_around_blocked_words(text, ["đm", "spam"])
    assert all(seg for seg, _ in segments)
    assert _reconstruct(segments) == text
    blocked_segments = [seg for seg, is_blocked in segments if is_blocked]
    assert blocked_segments == ["đm", "spam", "đm"]


def test_split_never_returns_empty_segments():
    text = "đmspam"  # not a real overlap scenario, but guards the invariant generally
    for segments in (
        split_around_blocked_words("đm đm", ["đm"]),
        split_around_blocked_words("", ["đm"]),
        split_around_blocked_words(text, []),
    ):
        assert all(seg != "" for seg, _ in segments)


# -- generate_beep_tone -----------------------------------------------------


def test_generate_beep_tone_shape_and_amplitude():
    sample_rate = 24_000
    duration = 0.3
    tone = generate_beep_tone(sample_rate, duration=duration)

    assert isinstance(tone, np.ndarray)
    assert tone.dtype == np.float32
    assert tone.ndim == 1
    assert tone.shape[0] == int(round(sample_rate * duration))
    assert np.max(np.abs(tone)) <= 1.0
    assert np.max(np.abs(tone)) > 0.05  # not silent


def test_generate_beep_tone_default_duration_and_custom_sample_rate():
    tone = generate_beep_tone(16_000)
    assert tone.shape[0] == int(round(16_000 * 0.3))


# -- parse_blocklist_file ----------------------------------------------------


def test_parse_blocklist_file_strips_blank_lines_and_whitespace():
    content = "đm\n\n  spam  \nbit.ly\n\n"
    assert parse_blocklist_file(content) == ["đm", "spam", "bit.ly"]


def test_parse_blocklist_file_dedups_preserving_first_order():
    content = "đm\nspam\nđm\n"
    assert parse_blocklist_file(content) == ["đm", "spam"]


# -- CommentFilter.is_duplicate ----------------------------------------------


def _comment(author: str, text: str, ts: float) -> Comment:
    return Comment(platform="tiktok", author=author, text=text, ts=ts)


def test_dedup_content_mode_catches_different_author_same_text(cfg):
    cfg.set("dedup_mode", "content")
    cfg.set("dedup_window_seconds", 10)
    filt = CommentFilter(cfg)

    assert filt.is_duplicate(_comment("alice", "hello", 100.0)) is False
    assert filt.is_duplicate(_comment("bob", "hello", 101.0)) is True


def test_dedup_author_mode_does_not_catch_different_author_same_text(cfg):
    cfg.set("dedup_mode", "author")
    cfg.set("dedup_window_seconds", 10)
    filt = CommentFilter(cfg)

    assert filt.is_duplicate(_comment("alice", "hello", 100.0)) is False
    assert filt.is_duplicate(_comment("bob", "hello", 101.0)) is False


def test_dedup_author_mode_catches_same_author_same_text(cfg):
    cfg.set("dedup_mode", "author")
    cfg.set("dedup_window_seconds", 10)
    filt = CommentFilter(cfg)

    assert filt.is_duplicate(_comment("alice", "hello", 100.0)) is False
    assert filt.is_duplicate(_comment("alice", "hello", 105.0)) is True


def test_dedup_entry_outside_window_is_not_flagged(cfg):
    cfg.set("dedup_mode", "content")
    cfg.set("dedup_window_seconds", 10)
    filt = CommentFilter(cfg)

    assert filt.is_duplicate(_comment("alice", "hello", 100.0)) is False
    # 20s later, well outside the 10s window.
    assert filt.is_duplicate(_comment("bob", "hello", 120.0)) is False


def test_dedup_different_text_never_flagged(cfg):
    cfg.set("dedup_mode", "content")
    cfg.set("dedup_window_seconds", 10)
    filt = CommentFilter(cfg)

    assert filt.is_duplicate(_comment("alice", "hello", 100.0)) is False
    assert filt.is_duplicate(_comment("alice", "goodbye", 101.0)) is False


def test_dedup_normalizes_text_before_comparing(cfg):
    cfg.set("dedup_mode", "content")
    filt = CommentFilter(cfg)

    assert filt.is_duplicate(_comment("alice", "Việt Nam", 100.0)) is False
    nfd_variant = unicodedata.normalize("NFD", "VIỆT NAM")
    assert filt.is_duplicate(_comment("bob", nfd_variant, 101.0)) is True


# -- CommentFilter blocklist helpers ------------------------------------------


def test_comment_filter_blocked_words_reads_live_config(cfg):
    filt = CommentFilter(cfg)
    assert filt.blocked_words("mày đm à") == []

    cfg.set("blocklist", ["đm"])
    assert filt.blocked_words("mày đm à") == ["đm"]


def test_comment_filter_should_bleep_reads_live_config(cfg):
    filt = CommentFilter(cfg)
    assert filt.should_bleep() is False

    cfg.set("blocklist_mode", "bleep")
    assert filt.should_bleep() is True


def test_comment_filter_split_for_bleep_uses_current_blocklist(cfg):
    cfg.set("blocklist", ["đm"])
    filt = CommentFilter(cfg)
    assert filt.split_for_bleep("mày đm à") == [("mày ", False), ("đm", True), (" à", False)]
