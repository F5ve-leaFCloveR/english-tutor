"""Backend TTS via OpenRouter (gpt-audio-mini), with WAV assembly + LRU cache."""
from __future__ import annotations

import base64
import hashlib
import logging
import wave
from collections import OrderedDict
from io import BytesIO

from openai import OpenAI

from tutor.budget import BudgetTracker

log = logging.getLogger(__name__)

_SAMPLE_RATE = 24000
_CHANNELS = 1
_SAMPLE_WIDTH = 2  # 16-bit


class TTSGenerationError(Exception):
    """Raised when the underlying TTS API call fails."""


class TTSService:
    def __init__(
        self,
        client: OpenAI,
        model: str,
        default_voice: str,
        budget: BudgetTracker,
        cache_capacity: int = 64,
    ) -> None:
        self._client = client
        self._model = model
        self._default_voice = default_voice
        self._budget = budget
        self._cache_capacity = cache_capacity
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        voice = voice or self._default_voice
        key = self._cache_key(text, voice)
        if key in self._cache:
            self._cache.move_to_end(key)  # mark recently used
            return self._cache[key]

        self._budget.check_can_spend()
        wav_bytes = self._generate(text, voice)
        self._cache[key] = wav_bytes
        if len(self._cache) > self._cache_capacity:
            self._cache.popitem(last=False)  # evict LRU
        return wav_bytes

    def _cache_key(self, text: str, voice: str) -> str:
        return hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()

    def _generate(self, text: str, voice: str) -> bytes:
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "user", "content": f"Say exactly this sentence: {text}"}
                ],
                modalities=["text", "audio"],
                audio={"voice": voice, "format": "pcm16"},
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as e:
            raise TTSGenerationError(f"TTS API call failed: {e}") from e

        pcm_chunks: list[bytes] = []
        usage = None
        try:
            for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                audio = getattr(delta, "audio", None)
                if audio:
                    data = audio.get("data") if isinstance(audio, dict) else getattr(audio, "data", None)
                    if data:
                        pcm_chunks.append(base64.b64decode(data))
        except Exception as e:
            raise TTSGenerationError(f"TTS stream decode failed: {e}") from e

        pcm = b"".join(pcm_chunks)
        if not pcm:
            raise TTSGenerationError("TTS returned no audio data")

        self._record_usage(usage)
        return self._wrap_wav(pcm)

    def _wrap_wav(self, pcm: bytes) -> bytes:
        buf = BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(_CHANNELS)
            w.setsampwidth(_SAMPLE_WIDTH)
            w.setframerate(_SAMPLE_RATE)
            w.writeframes(pcm)
        return buf.getvalue()

    def _record_usage(self, usage) -> None:
        if usage is None:
            return
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        cost = 0.0
        extra = getattr(usage, "model_extra", None) or {}
        if "cost" in extra:
            try:
                cost = float(extra["cost"])
            except (TypeError, ValueError):
                cost = 0.0
        self._budget.record(tokens_in=tokens_in, tokens_out=tokens_out, usd_cost=cost)
