"""Microphone recorder: press Enter to start, press Enter to stop."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

log = logging.getLogger(__name__)


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._buffer: list[np.ndarray] = []

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("sounddevice status: %s", status)
        self._buffer.append(indata.copy())

    def record_to_wav(self, out_path: Path) -> Path:
        """Block until user signals stop (Enter twice). Writes a WAV. Returns the path."""
        self._buffer = []
        input("[press Enter to start recording] ")
        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="float32",
            callback=self._on_audio,
        )
        with stream:
            stream.start()
            input("[recording... press Enter to stop] ")

        if not self._buffer:
            log.warning("No audio captured")
            audio = np.zeros((1, self._channels), dtype=np.float32)
        else:
            audio = np.concatenate(self._buffer, axis=0)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), audio, self._sample_rate)
        return out_path
