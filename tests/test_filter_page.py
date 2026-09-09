from __future__ import annotations

from cmtspeak.config import Config
from cmtspeak.ui.filter_page import FilterPage


def _page(qapp, tmp_path) -> tuple[FilterPage, Config]:
    cfg = Config(path=tmp_path / "config.json")
    return FilterPage(cfg), cfg


def test_adding_entry_saves_to_config_immediately(qapp, tmp_path):
    page, cfg = _page(qapp, tmp_path)

    page.blocklist_entry_edit.setText("spam")
    page._on_add_blocklist_entry()

    assert cfg.get("blocklist") == ["spam"]
    # A second Config instance reading the same file sees it too — proves
    # it was actually persisted to disk, not just held in memory.
    reloaded = Config(path=tmp_path / "config.json")
    assert reloaded.get("blocklist") == ["spam"]


def test_removing_entry_saves_to_config_immediately(qapp, tmp_path):
    page, cfg = _page(qapp, tmp_path)
    page.blocklist_entry_edit.setText("spam")
    page._on_add_blocklist_entry()

    page.blocklist_widget.setCurrentRow(0)
    page._on_remove_blocklist_entry()

    assert cfg.get("blocklist") == []


def test_changing_blocklist_mode_saves_immediately(qapp, tmp_path):
    page, cfg = _page(qapp, tmp_path)

    index = page.blocklist_mode_combo.findData("bleep")
    page.blocklist_mode_combo.setCurrentIndex(index)

    assert cfg.get("blocklist_mode") == "bleep"


def test_changing_dedup_window_saves_immediately(qapp, tmp_path):
    page, cfg = _page(qapp, tmp_path)

    page.dedup_window_spin.setValue(42)

    assert cfg.get("dedup_window_seconds") == 42


def test_loading_from_config_does_not_trigger_a_spurious_save(qapp, tmp_path, monkeypatch):
    cfg = Config(path=tmp_path / "config.json")
    cfg.set("blocklist", ["already-there"])
    cfg.set("blocklist_mode", "bleep")
    cfg.save()

    save_calls = []
    monkeypatch.setattr(Config, "save", lambda self: save_calls.append(True))

    page = FilterPage(cfg)

    assert page._blocklist_entries() == ["already-there"]
    assert save_calls == []
