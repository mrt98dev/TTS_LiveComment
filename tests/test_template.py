from __future__ import annotations

from cmtspeak.models import Comment
from cmtspeak.tts.template import DEFAULT_TEMPLATE, format_message


def _comment(author: str, text: str) -> Comment:
    return Comment(platform="mock", author=author, text=text, ts=0.0)


def test_default_template():
    c = _comment("Nguyễn Văn A", "giá bao nhiêu vậy shop")
    assert format_message(c, DEFAULT_TEMPLATE) == "Nguyễn Văn A nói: giá bao nhiêu vậy shop"


def test_content_only_template():
    c = _comment("Nguyễn Văn A", "giá bao nhiêu vậy shop")
    assert format_message(c, "{content}") == "giá bao nhiêu vậy shop"


def test_custom_prefix_suffix_template():
    c = _comment("A", "còn hàng không")
    result = format_message(c, "Bạn {name} vừa hỏi: {content}. Cảm ơn bạn!")
    assert result == "Bạn A vừa hỏi: còn hàng không. Cảm ơn bạn!"
