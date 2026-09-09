from __future__ import annotations

from cmtspeak.ui import theme


def test_load_icon_known_name_returns_non_null_icon(qapp) -> None:
    icon = theme.load_icon("play")
    assert not icon.isNull()
    assert icon.availableSizes()


def test_load_icon_unknown_name_returns_empty_icon(qapp) -> None:
    icon = theme.load_icon("does-not-exist")
    assert icon.isNull()


def test_load_icon_caches_by_name_color_size(qapp) -> None:
    first = theme.load_icon("play", color="#ffffff", size=20)
    second = theme.load_icon("play", color="#ffffff", size=20)
    assert first is second

    different_color = theme.load_icon("play", color="#000000", size=20)
    assert different_color is not first
