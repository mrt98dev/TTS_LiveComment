from __future__ import annotations

import logging
from typing import Iterable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


def list_output_devices() -> list[tuple[int, str]]:
    """Return ``(device_index, device_name)`` for every device that has at
    least one output channel, as reported by ``sounddevice.query_devices()``.
    Suitable for populating a device-selection dropdown."""
    devices = sd.query_devices()
    return [
        (index, str(device.get("name", f"Device {index}")))
        for index, device in enumerate(devices)
        if device.get("max_output_channels", 0) > 0
    ]


class AudioOutput:
    """Plays a stream of float32 mono audio chunks to a sounddevice output
    device, choosing a device/sample-rate fresh on each call so changes made
    between comments take effect immediately."""

    def play_stream(
        self,
        chunks: Iterable[np.ndarray],
        sample_rate: int,
        device: Optional[int] = None,
    ) -> None:
        """Consume every chunk from a streaming TTS generator, concatenate
        them into one buffer, and play the whole thing in a single
        continuous pass, blocking until playback finishes.

        VieNeu-TTS's infer_stream() only smooths the boundary *between*
        normalized text chunks (sentences/phrases); the sub-chunks the
        underlying engine streams out *within* one chunk are handed back
        as-is. Writing each of those straight to a live OutputStream one
        `stream.write()` call at a time is audibly glitchy — heard as
        stutter between words — whenever there's any hiccup in the timing
        between writes. Buffering the whole utterance first and handing it
        to the audio backend as one array sidesteps that entirely: there is
        only one buffer and no write-to-write boundary left for a gap to
        appear at. The tradeoff is a short wait for the full comment to
        finish synthesizing before playback starts, instead of the ~300ms
        streaming start VieNeu-TTS advertises — an easy trade here, since
        comments are already read one at a time off a queue rather than
        needing sub-second responsiveness.
        """
        buffers = []
        for chunk in chunks:
            if chunk is None:
                continue
            data = np.asarray(chunk, dtype=np.float32)
            if data.size == 0:
                continue
            buffers.append(data)

        if not buffers:
            return

        audio = buffers[0] if len(buffers) == 1 else np.concatenate(buffers)
        sd.play(audio, samplerate=sample_rate, device=device, blocking=True)

    def stop(self) -> None:
        """Halt whatever is currently playing via sd.play(). Safe to call
        from any thread, including while another thread is blocked inside
        play_stream()'s blocking=True sd.play() call — that call returns as
        soon as this is invoked, since sd.stop() halts the stream sd.wait()
        (which blocking=True uses internally) is watching. A no-op if
        nothing is currently playing."""
        sd.stop()
