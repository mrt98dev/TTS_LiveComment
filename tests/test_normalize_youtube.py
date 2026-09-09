from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from cmtspeak.connectors.youtube_connector import extract_video_id, normalize_message
from cmtspeak.models import Comment

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "youtube_liveChatMessage.json"


def _load_fixture_items() -> list[dict]:
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["items"]


def test_normalize_message_first_item():
    items = _load_fixture_items()
    comment = normalize_message(items[0])

    assert isinstance(comment, Comment)
    assert comment.platform == "youtube"
    assert comment.author == "Nguyễn Văn A"
    assert comment.text == "Chào shop, giá bao nhiêu vậy ạ?"
    expected_ts = datetime.fromisoformat("2026-09-09T10:15:30.500+00:00").timestamp()
    assert comment.ts == pytest.approx(expected_ts)


def test_normalize_message_second_item():
    items = _load_fixture_items()
    comment = normalize_message(items[1])

    assert comment.platform == "youtube"
    assert comment.author == "Trần Thị B"
    assert comment.text == "Còn size M không shop ơi?"


def test_normalize_message_missing_display_message_falls_back_to_text_details():
    item = {
        "snippet": {
            "publishedAt": "2026-09-09T10:00:00.000Z",
            "textMessageDetails": {"messageText": "fallback text"},
        },
        "authorDetails": {"displayName": "Someone"},
    }
    comment = normalize_message(item)
    assert comment.text == "fallback text"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=XXXX",
        "https://youtu.be/XXXX",
        "https://www.youtube.com/live/XXXX",
        "XXXX",
    ],
)
def test_extract_video_id(url: str):
    assert extract_video_id(url) == "XXXX"


def test_extract_video_id_watch_with_extra_query_params():
    assert extract_video_id("https://www.youtube.com/watch?v=XXXX&t=30s") == "XXXX"


def test_extract_video_id_empty_raises():
    with pytest.raises(ValueError):
        extract_video_id("")
