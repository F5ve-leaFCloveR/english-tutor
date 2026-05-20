from unittest.mock import MagicMock
from pathlib import Path


def test_asr_transcribes_wav_file(mocker, tmp_path):
    from tutor.asr import WhisperASR

    fake_segment = MagicMock()
    fake_segment.text = "Hello, how are you?"
    fake_info = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter([fake_segment]), fake_info)

    fake_loader = mocker.patch("tutor.asr.WhisperModel", return_value=fake_model)

    asr = WhisperASR(model_size="small")
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"")

    text = asr.transcribe(wav_path)
    assert text == "Hello, how are you?"
    fake_loader.assert_called_once()
    fake_model.transcribe.assert_called_once_with(
        str(wav_path),
        language="en",
        beam_size=5,
    )


def test_asr_joins_multiple_segments(mocker, tmp_path):
    from tutor.asr import WhisperASR

    s1 = MagicMock(); s1.text = "Hello,"
    s2 = MagicMock(); s2.text = " how are you?"
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter([s1, s2]), MagicMock())
    mocker.patch("tutor.asr.WhisperModel", return_value=fake_model)

    asr = WhisperASR(model_size="small")
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"")
    text = asr.transcribe(wav_path)
    assert text == "Hello, how are you?"


def test_asr_model_loaded_only_once(mocker, tmp_path):
    from tutor.asr import WhisperASR

    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter([]), MagicMock())
    loader = mocker.patch("tutor.asr.WhisperModel", return_value=fake_model)

    asr = WhisperASR(model_size="small")
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"")
    asr.transcribe(wav_path)
    asr.transcribe(wav_path)
    assert loader.call_count == 1
