from __future__ import annotations

from PySide6.QtTest import QTest

from cmtspeak.config import Config
from cmtspeak.ui.general_page import GeneralPage


def _page(qapp, tmp_path) -> tuple[GeneralPage, Config]:
    cfg = Config(path=tmp_path / "config.json")
    return GeneralPage(cfg), cfg


def test_changing_skip_mode_saves_immediately(qapp, tmp_path):
    page, cfg = _page(qapp, tmp_path)

    index = page.skip_mode_combo.findData("next_only")
    page.skip_mode_combo.setCurrentIndex(index)

    assert cfg.get("skip_mode") == "next_only"


def test_loading_from_config_does_not_trigger_a_spurious_save(qapp, tmp_path, monkeypatch):
    cfg = Config(path=tmp_path / "config.json")
    cfg.set("skip_mode", "next_only")
    cfg.set("template", "{name}: {content}")
    cfg.save()

    save_calls = []
    monkeypatch.setattr(Config, "save", lambda self: save_calls.append(True))

    GeneralPage(cfg)

    assert save_calls == []


def test_typing_template_debounces_to_a_single_save(qapp, tmp_path):
    page, cfg = _page(qapp, tmp_path)

    page.template_edit.setText("{")
    page.template_edit.setText("{n")
    page.template_edit.setText("{name} nói {content}")

    # Nothing saved yet — still inside the debounce window.
    assert cfg.get("template") != "{name} nói {content}"

    QTest.qWait(400)

    assert cfg.get("template") == "{name} nói {content}"


def test_typing_api_key_debounces_to_a_single_save(qapp, tmp_path):
    page, cfg = _page(qapp, tmp_path)

    page.api_key_edit.setText("A")
    page.api_key_edit.setText("AB")
    page.api_key_edit.setText("ABC123")

    QTest.qWait(400)

    assert cfg.get("youtube_api_key") == "ABC123"
