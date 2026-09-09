from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Comment:
    platform: str
    author: str
    text: str
    ts: float
