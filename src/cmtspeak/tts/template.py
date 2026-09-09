from __future__ import annotations

from cmtspeak.models import Comment

DEFAULT_TEMPLATE = "{name} nói: {content}"


def format_message(comment: Comment, template: str = DEFAULT_TEMPLATE) -> str:
    """Build the sentence to be spoken for a comment, from a user-editable
    template. Only {name} and {content} are recognized placeholders; any other
    text in the template is kept as-is (prefix/suffix)."""
    return template.format(name=comment.author, content=comment.text)
