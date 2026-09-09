from __future__ import annotations

import pytest

from cmtspeak.config import Config
from cmtspeak.tts import voice_manager as voice_manager_module
from cmtspeak.tts.voice_manager import VoiceManager


class FakeEngine:
    """Stand-in for vieneu.Vieneu(): no real model, no real audio.

    Mirrors the real engine's important quirk: a genuine built-in preset
    always carries a real `description`, while `add_voice()` called without
    one (exactly how VoiceManager.add_clone_voice calls it) leaves it `""`.
    That distinction is what list_voices() uses to tell clones apart from
    built-ins — not the voice's name.
    """

    def __init__(self) -> None:
        self.sample_rate = 48_000
        # Baseline "built-in" presets, shaped like real ones: real description.
        self._preset_voices: dict[str, dict] = {
            "voice_a": {"description": "Nữ · Bắc · Phong cách tự nhiên"},
            "voice_b": {"description": "Nam · Nam · Phong cách kể chuyện"},
        }
        self.add_voice_calls: list[tuple[str, str, bool]] = []
        self.remove_voice_calls: list[tuple[str, bool]] = []
        self.save_voices_calls = 0

    def list_preset_voices(self) -> list[tuple[str, str]]:
        return [(v.get("description") or k, k) for k, v in self._preset_voices.items()]

    def add_voice(self, name: str, ref_audio: str, denoise: bool = True) -> None:
        self.add_voice_calls.append((name, ref_audio, denoise))
        self._preset_voices[name] = {"description": ""}  # matches real vieneu's default

    def remove_voice(self, name: str, save: bool = False) -> None:
        self.remove_voice_calls.append((name, save))
        self._preset_voices.pop(name, None)

    def save_voices(self) -> None:
        self.save_voices_calls += 1

    def infer_stream(self, text: str, voice=None):
        yield b"chunk-for-" + text.encode()


@pytest.fixture
def cfg(tmp_path):
    return Config(path=tmp_path / "config.json")


@pytest.fixture
def fake_engine(monkeypatch):
    engine = FakeEngine()
    # VoiceManager builds the engine lazily via `vieneu.Vieneu()`; stub the
    # factory function so no real model is ever constructed.
    monkeypatch.setattr(voice_manager_module.vieneu, "Vieneu", lambda *a, **k: engine)
    return engine


def test_engine_not_constructed_until_first_use(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        voice_manager_module.vieneu,
        "Vieneu",
        lambda *a, **k: calls.append(1) or FakeEngine(),
    )
    VoiceManager(cfg)
    assert calls == []  # __init__ alone must not build the model


def test_add_clone_voice_calls_vieneu_and_persists_after_list_voices(cfg, fake_engine):
    manager = VoiceManager(cfg)

    manager.add_clone_voice("MyClone", "/tmp/sample.wav")

    assert fake_engine.add_voice_calls == [("MyClone", "/tmp/sample.wav", True)]
    assert fake_engine.save_voices_calls == 1

    # clone_voice_names is recomputed by list_voices(), not by add_clone_voice
    # itself — the UI always refreshes right after, so this is the contract.
    manager.list_voices()
    assert cfg.get("clone_voice_names") == ["MyClone"]

    reloaded = Config(path=cfg._path)
    assert reloaded.get("clone_voice_names") == ["MyClone"]


def test_remove_clone_voice_persists_and_drops_from_tracking(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("MyClone", "/tmp/sample.wav")
    manager.list_voices()
    assert cfg.get("clone_voice_names") == ["MyClone"]

    manager.remove_clone_voice("MyClone")

    # save=True is required — vieneu's remove_voice() defaults to in-memory
    # only, and without persisting, the "removed" voice reappears from the
    # engine's saved voices file on the next launch (this was a real,
    # reported bug: it vanished from clone_voice_names but not from disk).
    assert fake_engine.remove_voice_calls == [("MyClone", True)]

    manager.list_voices()
    assert cfg.get("clone_voice_names") == []


def test_list_voices_classifies_by_description_not_by_name(cfg, fake_engine):
    """Regression test for a real reported bug: an earlier version
    identified "genuine built-in" voices with a hardcoded name list, which
    broke the moment the installed vieneu package shipped built-in voices
    that list didn't know about — they got wrongly tagged as clones.
    Classification must instead follow each voice's own `description`
    metadata (empty only for clones we ourselves add), which stays correct
    no matter what the built-in roster looks like."""
    # A voice that looks exactly like a real built-in (has a description) —
    # even though it's not one of the fixture's original two — must not be
    # treated as a clone.
    fake_engine._preset_voices["Giọng Mới Của Hãng"] = {"description": "Nam · Bắc · Phong cách tự nhiên"}

    manager = VoiceManager(cfg)
    voices = manager.list_voices()
    ids = [voice_id for _, voice_id in voices]

    assert "Giọng Mới Của Hãng" in ids
    assert cfg.get("clone_voice_names") == []
    assert manager.is_clone_voice("Giọng Mới Của Hãng") is False


def test_list_voices_drops_ghost_names_no_longer_in_engine(cfg, fake_engine):
    """A name can linger in clone_voice_names after being genuinely removed
    (e.g. from before the remove_clone_voice persistence fix). Since
    list_voices() recomputes tracking from the engine's live state, a name
    with nothing behind it must not keep showing up as an unusable
    "phantom" clone entry."""
    cfg.set("clone_voice_names", ["GhostClone"])
    cfg.save()

    manager = VoiceManager(cfg)
    voices = manager.list_voices()

    ids = [voice_id for _, voice_id in voices]
    assert "GhostClone" not in ids
    assert cfg.get("clone_voice_names") == []


def test_list_voices_reclassifies_previously_mistracked_builtin(cfg, fake_engine):
    """If a real built-in voice was incorrectly recorded as a clone by an
    earlier bug, list_voices() must correct that too, not just add missing
    entries."""
    cfg.set("clone_voice_names", ["voice_a"])  # voice_a has a real description
    cfg.save()

    manager = VoiceManager(cfg)
    manager.list_voices()

    assert cfg.get("clone_voice_names") == []
    assert manager.is_clone_voice("voice_a") is False


def test_infer_stream_passes_through_to_engine(cfg, fake_engine):
    manager = VoiceManager(cfg)

    chunks = list(manager.infer_stream("Xin chào", voice="voice_a"))

    assert chunks == [b"chunk-for-Xin ch\xc3\xa0o"]
    assert manager.sample_rate == 48_000


def test_is_clone_voice_after_list_voices(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("MyClone", "/tmp/sample.wav")
    manager.list_voices()

    assert manager.is_clone_voice("MyClone") is True
    assert manager.is_clone_voice("voice_a") is False


def test_update_clone_voice_rename_only_keeps_existing_embedding(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("OldName", "/tmp/sample.wav")
    manager.list_voices()

    manager.update_clone_voice("OldName", "NewName")

    assert "NewName" in fake_engine._preset_voices
    assert "OldName" not in fake_engine._preset_voices
    # No re-enrollment happened — only the one add_voice call from add_clone_voice.
    assert fake_engine.add_voice_calls == [("OldName", "/tmp/sample.wav", True)]

    manager.list_voices()
    assert cfg.get("clone_voice_names") == ["NewName"]

    reloaded = Config(path=cfg._path)
    assert reloaded.get("clone_voice_names") == ["NewName"]


def test_update_clone_voice_with_new_audio_reenrolls_under_new_name(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("OldName", "/tmp/sample.wav")

    manager.update_clone_voice("OldName", "NewName", "/tmp/new_sample.wav")

    assert fake_engine.add_voice_calls[-1] == ("NewName", "/tmp/new_sample.wav", True)
    assert fake_engine.remove_voice_calls == [("OldName", True)]

    manager.list_voices()
    assert cfg.get("clone_voice_names") == ["NewName"]


def test_update_clone_voice_same_name_new_audio_reenrolls_in_place(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("SameName", "/tmp/sample.wav")

    manager.update_clone_voice("SameName", "SameName", "/tmp/new_sample.wav")

    assert fake_engine.add_voice_calls[-1] == ("SameName", "/tmp/new_sample.wav", True)
    assert fake_engine.remove_voice_calls == []  # never removed, just re-added

    manager.list_voices()
    assert cfg.get("clone_voice_names") == ["SameName"]


def test_update_clone_voice_updates_selected_voice_when_renamed(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("OldName", "/tmp/sample.wav")
    cfg.set("selected_voice", "OldName")
    cfg.save()

    manager.update_clone_voice("OldName", "NewName")

    assert cfg.get("selected_voice") == "NewName"


def test_update_clone_voice_rejects_empty_name(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("OldName", "/tmp/sample.wav")

    with pytest.raises(ValueError):
        manager.update_clone_voice("OldName", "   ")


def test_update_clone_voice_rejects_collision_with_existing_name(cfg, fake_engine):
    manager = VoiceManager(cfg)
    manager.add_clone_voice("First", "/tmp/sample.wav")
    manager.add_clone_voice("Second", "/tmp/sample2.wav")

    with pytest.raises(ValueError):
        manager.update_clone_voice("First", "Second")
