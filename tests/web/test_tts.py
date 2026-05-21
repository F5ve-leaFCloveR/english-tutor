import base64
import wave
from datetime import datetime
from io import BytesIO
from unittest.mock import MagicMock
import pytest


def _make_budget(tmp_path):
    from tutor.budget import BudgetTracker
    return BudgetTracker(
        path=tmp_path / "b.json",
        daily_usd_cap=1.0,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 12, 0),
    )


def _stub_pcm_stream(pcm_bytes: bytes, cost: float = 0.0):
    """Yield SSE-like chunks: first chunks deliver audio data (base64), final has usage."""
    # Split PCM into two halves for realism
    half = len(pcm_bytes) // 2
    chunk1, chunk2 = pcm_bytes[:half], pcm_bytes[half:]

    def make_audio_chunk(b: bytes):
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta = MagicMock()
        c.choices[0].delta.audio = {"data": base64.b64encode(b).decode("ascii")}
        c.usage = None
        return c

    final = MagicMock()
    final.choices = [MagicMock()]
    final.choices[0].delta = MagicMock()
    final.choices[0].delta.audio = None
    final.usage = MagicMock()
    final.usage.prompt_tokens = 50
    final.usage.completion_tokens = 100
    final.usage.total_tokens = 150
    final.usage.model_extra = {"cost": cost}

    return iter([make_audio_chunk(chunk1), make_audio_chunk(chunk2), final])


def test_tts_service_returns_wav_bytes(tmp_path):
    from tutor.web.tts import TTSService

    pcm = b"\x01\x02" * 1000  # arbitrary PCM16 mono data
    client = MagicMock()
    client.chat.completions.create.return_value = _stub_pcm_stream(pcm, cost=0.0001)

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    wav_bytes = svc.synthesize("hello", voice="alloy")

    # Verify it's a valid WAV
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"
    with wave.open(BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 24000
        assert w.getsampwidth() == 2  # 16-bit
        # Frames should equal PCM byte count / 2 (16-bit samples)
        assert w.getnframes() == len(pcm) // 2


def test_tts_service_caches_by_text_and_voice(tmp_path):
    from tutor.web.tts import TTSService

    pcm = b"\x03\x04" * 500
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _stub_pcm_stream(pcm),
        _stub_pcm_stream(b"different" * 100),  # would differ if cache missed
    ]

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    a = svc.synthesize("hello", voice="alloy")
    b = svc.synthesize("hello", voice="alloy")
    assert a == b
    assert client.chat.completions.create.call_count == 1  # second hit cache


def test_tts_service_cache_key_includes_voice(tmp_path):
    from tutor.web.tts import TTSService

    pcm_a = b"AA" * 200
    pcm_b = b"BB" * 200
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _stub_pcm_stream(pcm_a),
        _stub_pcm_stream(pcm_b),
    ]

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    a = svc.synthesize("hello", voice="alloy")
    b = svc.synthesize("hello", voice="nova")
    assert a != b
    assert client.chat.completions.create.call_count == 2


def test_tts_service_default_voice_used_when_none(tmp_path):
    from tutor.web.tts import TTSService

    pcm = b"\x00\x01" * 100
    client = MagicMock()
    client.chat.completions.create.return_value = _stub_pcm_stream(pcm)

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    svc.synthesize("hi", voice=None)

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["audio"]["voice"] == "alloy"


def test_tts_service_lru_eviction(tmp_path):
    from tutor.web.tts import TTSService

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _stub_pcm_stream(b"\x01\x02" * 100) for _ in range(5)
    ]
    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
        cache_capacity=2,
    )

    svc.synthesize("a", voice="alloy")
    svc.synthesize("b", voice="alloy")
    svc.synthesize("c", voice="alloy")  # evicts "a"
    svc.synthesize("a", voice="alloy")  # re-generates, not cached

    # 4 unique generations, none was a cache hit when re-asking for "a"
    assert client.chat.completions.create.call_count == 4


def test_tts_service_propagates_budget_error(tmp_path):
    from tutor.web.tts import TTSService
    from tutor.budget import BudgetTracker, BudgetExceededError

    budget = BudgetTracker(
        path=tmp_path / "b.json",
        daily_usd_cap=0.00001,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 12, 0),
    )
    budget.record(tokens_in=10, tokens_out=10, usd_cost=0.001)  # already over

    svc = TTSService(
        client=MagicMock(),
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=budget,
    )

    with pytest.raises(BudgetExceededError):
        svc.synthesize("hello", voice="alloy")


def test_tts_service_wraps_api_error(tmp_path):
    from tutor.web.tts import TTSService, TTSGenerationError

    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("openrouter down")

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    with pytest.raises(TTSGenerationError):
        svc.synthesize("hello", voice="alloy")
