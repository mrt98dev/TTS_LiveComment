from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from cmtspeak.audio.output import AudioOutput
from cmtspeak.config import Config
from cmtspeak.tts import voice_manager as voice_manager_module
from cmtspeak.tts.voice_manager import VoiceManager
from cmtspeak.ui.voices_page import VoicesPage


class _FakeEngine:
    def __init__(self) -> None:
        self.sample_rate = 48_000
        self._preset_voices = {
            "voice_a": {"description": "Nữ · Bắc"},
            "voice_b": {"description": "Nam · Nam"},
        }

    def list_preset_voices(self):
        return [(v.get("description") or k, k) for k, v in self._preset_voices.items()]

    def add_voice(self, name, ref_audio, denoise=True):
        self._preset_voices[name] = {"description": ""}

    def remove_voice(self, name, save=False):
        self._preset_voices.pop(name, None)

    def save_voices(self) -> None:
        pass


@pytest.fixture
def fake_engine(monkeypatch):
    engine = _FakeEngine()
    monkeypatch.setattr(voice_manager_module.vieneu, "Vieneu", lambda *a, **k: engine)
    return engine


@pytest.fixture
def page(qapp, tmp_path, fake_engine):
    cfg = Config(path=tmp_path / "config.json")
    voices = VoiceManager(cfg)
    audio = AudioOutput()
    widget = VoicesPage(cfg, voices, audio)
    # Let the background _VoiceListLoader (started in __init__) finish, then
    # populate again synchronously so the test doesn't race its signal
    # delivery (which needs a running Qt event loop to arrive).
    widget._voice_loader.wait(2000)
    widget._populate_voice_list(voices.list_voices())
    return widget, cfg


def test_selecting_a_voice_saves_immediately(page):
    widget, cfg = page

    widget.voice_list.setCurrentRow(1)

    selected_id = widget.voice_list.currentItem().data(Qt.UserRole)
    assert cfg.get("selected_voice") == selected_id


def test_populate_marks_clone_voices_via_item_data(page):
    widget, cfg = page

    for i in range(widget.voice_list.count()):
        item = widget.voice_list.item(i)
        assert item.data(Qt.UserRole + 1) is False  # no clones yet
