from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = Path.home() / ".cmt-speak"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"

_DEFAULTS: dict[str, Any] = {
    "template": "{name} nói: {content}",
    "selected_voice": None,
    "audio_output_device": None,
    "youtube_api_key": "",
    "clone_voice_names": [],
    "skip_mode": "interrupt",
    "blocklist": [],
    "blocklist_mode": "skip",
    "dedup_mode": "content",
    "dedup_window_seconds": 10,
}


class Config:
    """Small JSON-backed settings store shared by every part of the app
    (voice manager, connectors, UI). Unknown keys are ignored on load so
    older config files stay forward-compatible."""

    def __init__(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        self._path = path
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self.load()

    def load(self) -> None:
        if self._path.exists():
            stored = json.loads(self._path.read_text(encoding="utf-8"))
            self._data.update({k: v for k, v in stored.items() if k in _DEFAULTS})

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, key: str) -> Any:
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        if key not in _DEFAULTS:
            raise KeyError(f"Unknown config key: {key}")
        self._data[key] = value
