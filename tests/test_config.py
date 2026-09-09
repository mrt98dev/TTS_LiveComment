from __future__ import annotations

from pathlib import Path

from cmtspeak.config import Config


def test_defaults_when_no_file(tmp_path: Path):
    cfg = Config(path=tmp_path / "config.json")
    assert cfg.get("template") == "{name} nói: {content}"
    assert cfg.get("clone_voice_names") == []
    assert cfg.get("skip_mode") == "interrupt"


def test_save_and_reload_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config(path=path)
    cfg.set("template", "{content}")
    cfg.set("youtube_api_key", "secret-key")
    cfg.set("clone_voice_names", ["Giọng của tôi"])
    cfg.set("skip_mode", "next_only")
    cfg.save()

    reloaded = Config(path=path)
    assert reloaded.get("template") == "{content}"
    assert reloaded.get("youtube_api_key") == "secret-key"
    assert reloaded.get("clone_voice_names") == ["Giọng của tôi"]
    assert reloaded.get("skip_mode") == "next_only"


def test_unknown_key_rejected(tmp_path: Path):
    cfg = Config(path=tmp_path / "config.json")
    try:
        cfg.set("does_not_exist", 1)
        assert False, "expected KeyError"
    except KeyError:
        pass
