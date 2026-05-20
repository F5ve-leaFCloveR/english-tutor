"""faster-whisper adapter for English-only short-clip transcription."""
from __future__ import annotations

import logging
from pathlib import Path

from faster_whisper import WhisperModel

log = logging.getLogger(__name__)


class WhisperASR:
    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8") -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: WhisperModel | None = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            log.info("Loading faster-whisper model: %s (%s)", self._model_size, self._device)
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def transcribe(self, wav_path: Path) -> str:
        model = self._ensure_model()
        segments, _info = model.transcribe(
            str(wav_path),
            language="en",
            beam_size=5,
        )
        return "".join(seg.text for seg in segments).strip()
