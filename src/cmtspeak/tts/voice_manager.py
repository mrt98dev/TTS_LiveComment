from __future__ import annotations

import logging
import threading
from typing import Iterator, Optional

import numpy as np
import vieneu

from cmtspeak.config import Config

logger = logging.getLogger(__name__)


def _construct_engine():
    """Build the vieneu engine, preferring the local Hugging Face cache.

    With the model already cached (the normal case after the first run),
    vieneu's default construction still makes unauthenticated Hugging Face
    Hub network calls to check for updates — measured at ~100s, vs. ~2s
    offline. So: try offline first, and only allow network access as a
    fallback for a genuine first run with no local cache yet.

    This flips `huggingface_hub.constants.HF_HUB_OFFLINE` directly rather
    than the HF_HUB_OFFLINE *environment variable*: huggingface_hub reads
    the env var into that module attribute exactly once, at import time,
    and every later check (including the one voice cloning's speaker-
    encoder download hits) reads the attribute, not the environment. The
    first version of this function only toggled the env var and restored it
    afterward — since vieneu's own first import of huggingface_hub happens
    inside that same call, the attribute got permanently stuck at True, and
    voice cloning (which needs a real, separate download the very first
    time it's used) failed forever after with "offline mode is enabled",
    even on a network-connected machine. Toggling the attribute itself
    keeps every later huggingface_hub call honest about actual online/
    offline intent.
    """
    import huggingface_hub.constants as hf_constants

    previous = hf_constants.HF_HUB_OFFLINE
    hf_constants.HF_HUB_OFFLINE = True
    try:
        return vieneu.Vieneu()
    except Exception:
        logger.info("Model not cached locally yet — downloading from Hugging Face...")
    finally:
        hf_constants.HF_HUB_OFFLINE = previous
    return vieneu.Vieneu()


class VoiceManager:
    """Wraps a `vieneu.Vieneu` engine instance: preset voices, voice cloning,
    and streaming inference for the TTS worker.

    `vieneu.Vieneu()` loads a real model on construction (and may download it
    from HuggingFace on first run), so we do not build it in `__init__` or at
    import time. The engine is built lazily on first real use (listing voices,
    adding/removing a clone, or running inference) via the `engine` property.
    In the app, both a UI-side loader thread and the TTS worker thread can
    reach this property around the same time (e.g. at startup), so
    construction is guarded by a lock rather than a plain None-check.
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._engine = None
        self._engine_lock = threading.Lock()

    @property
    def engine(self):
        """The underlying `vieneu.Vieneu` instance, constructed on first access."""
        if self._engine is None:
            with self._engine_lock:
                if self._engine is None:
                    logger.info("Loading VieNeu-TTS engine (first use)...")
                    self._engine = _construct_engine()
        return self._engine

    @property
    def sample_rate(self) -> int:
        return self.engine.sample_rate

    def list_voices(self) -> list[tuple[str, str]]:
        """Return `(label, voice_id)` pairs for every voice usable as
        `infer_stream(..., voice=voice_id)`.

        Also recomputes `Config`'s `clone_voice_names` from the engine's own
        state on every call, using each voice's `description` metadata as
        the signal: `add_clone_voice`/`update_clone_voice` never set one, so
        it stays `""`, while every genuine VieNeu-TTS built-in ships with a
        real one (e.g. "Nam · Bắc · Phong cách tự nhiên"). This is
        intentionally NOT a hardcoded list of "known built-in names" — an
        earlier version of this method used one, and it broke the first
        time vieneu shipped a build with more built-in voices than that
        list knew about, wrongly relabeling real presets as clones.
        Recomputing from live engine metadata also self-heals the reverse
        problem: a name that lingers in `clone_voice_names` after being
        genuinely removed (or added under a since-reverted engine state)
        naturally drops out, since it's no longer a real entry to check.
        """
        voices = list(self.engine.list_preset_voices())
        raw_voices: dict = getattr(self.engine, "_preset_voices", {})

        clone_ids = sorted(
            voice_id for voice_id in raw_voices if not (raw_voices[voice_id].get("description") or "").strip()
        )
        if clone_ids != self._cfg.get("clone_voice_names"):
            self._cfg.set("clone_voice_names", clone_ids)
            self._cfg.save()

        return voices

    def add_clone_voice(self, name: str, wav_path: str) -> None:
        """Enroll a new cloned voice from a 3-8s reference wav and persist it
        via `vieneu.save_voices()`. `Config`'s `clone_voice_names` is
        recomputed from the engine's own state the next time `list_voices()`
        runs (call it, e.g. via a UI refresh, right after this)."""
        self.engine.add_voice(name, wav_path, denoise=True)
        self.engine.save_voices()

    def remove_clone_voice(self, name: str) -> None:
        """Remove a cloned voice from the engine.

        vieneu's remove_voice() defaults to save=False (in-memory only) —
        passing save=True here is required, or the removal only lasts for
        the current session: the next launch reloads the engine's saved
        voices file, which would still have the "removed" voice in it.
        """
        self.engine.remove_voice(name, save=True)

    def is_clone_voice(self, voice_id: str) -> bool:
        """Only accurate as of the last `list_voices()` call, which is what
        actually (re)computes `clone_voice_names` — see there."""
        return voice_id in self._cfg.get("clone_voice_names")

    def update_clone_voice(self, old_name: str, new_name: str, new_wav_path: Optional[str] = None) -> None:
        """Rename a cloned voice and/or re-enroll it from a new reference
        clip. If `new_wav_path` is given, the voice is simply re-added under
        `new_name` (this re-embeds from the new audio) and the old entry is
        dropped if the name changed. Otherwise only the name changes: vieneu
        has no public rename API, so this moves the entry directly inside
        the engine's voice dict (keeping the existing embedding/codes and
        its metadata, avoiding a need for the original reference audio) and
        re-persists.
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Tên giọng không được để trống.")

        if new_wav_path:
            self.add_clone_voice(new_name, new_wav_path)
            if new_name != old_name:
                self.remove_clone_voice(old_name)
        elif new_name != old_name:
            voices = self.engine._preset_voices  # no public rename API
            if old_name not in voices:
                raise ValueError(f"Không tìm thấy giọng '{old_name}'.")
            if new_name in voices:
                raise ValueError(f"Giọng '{new_name}' đã tồn tại.")
            voices[new_name] = voices.pop(old_name)
            self.engine.save_voices()

        if new_name != old_name and self._cfg.get("selected_voice") == old_name:
            self._cfg.set("selected_voice", new_name)
            self._cfg.save()

    def infer_stream(self, text: str, voice: Optional[str] = None) -> Iterator[np.ndarray]:
        """Thin passthrough to `vieneu.infer_stream`, for the TTS worker to
        consume chunk by chunk."""
        return self.engine.infer_stream(text, voice=voice)
