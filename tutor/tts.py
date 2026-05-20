"""macOS `say` TTS adapter."""
from __future__ import annotations

import subprocess


class MacSayTTS:
    def __init__(self, voice: str = "Samantha", rate: int = 180) -> None:
        self._voice = voice
        self._rate = rate

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        subprocess.run(
            ["say", "-v", self._voice, "-r", str(self._rate), text],
            check=False,
        )
