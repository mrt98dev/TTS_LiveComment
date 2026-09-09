from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from cmtspeak.connectors.tiktok_connector import normalize_comment_event
from cmtspeak.models import Comment

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tiktok_comment.json"


def _load_fixture_items() -> list[dict]:
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _make_event(item: dict) -> SimpleNamespace:
    """Build a lightweight stand-in for a real `TikTokLive` `CommentEvent`:
    an object exposing `.content` (str) and `.user` (with `.nickname` /
    `.display_id`), matching the shape the actual library's `CommentEvent`
    and `ExtendedUser` classes expose. No TikTokLive import or asyncio
    connection is needed to build or use this."""
    user_data = item.get("user") or {}
    user = SimpleNamespace(**user_data) if user_data else None
    return SimpleNamespace(content=item.get("content", ""), user=user)


def test_normalize_comment_event_first_item():
    items = _load_fixture_items()
    event = _make_event(items[0])
    comment = normalize_comment_event(event)

    assert isinstance(comment, Comment)
    assert comment.platform == "tiktok"
    assert comment.author == "Nguyễn Văn A"
    assert comment.text == "Giá bao nhiêu vậy shop ơi?"
    assert isinstance(comment.ts, float)


def test_normalize_comment_event_second_item_with_emoji():
    items = _load_fixture_items()
    event = _make_event(items[1])
    comment = normalize_comment_event(event)

    assert comment.platform == "tiktok"
    assert comment.author == "Trần Thị B"
    assert comment.text == "Còn size M không ạ 😊"


def test_normalize_comment_event_missing_nickname_falls_back_to_display_id():
    event = SimpleNamespace(content="hello", user=SimpleNamespace(nickname=None, display_id="handle123"))
    comment = normalize_comment_event(event)
    assert comment.author == "handle123"


def test_normalize_comment_event_missing_user_falls_back_to_unknown():
    event = SimpleNamespace(content="hello", user=None)
    comment = normalize_comment_event(event)
    assert comment.author == "Unknown"
    assert comment.text == "hello"


def test_normalize_comment_event_missing_content_falls_back_to_empty_string():
    event = SimpleNamespace(content=None, user=SimpleNamespace(nickname="Someone"))
    comment = normalize_comment_event(event)
    assert comment.text == ""
