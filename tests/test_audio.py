from unittest.mock import MagicMock, patch
from pathlib import Path
import numpy as np


def test_audio_recorder_records_to_wav(mocker, tmp_path):
    from tutor.audio import AudioRecorder

    fake_stream = MagicMock()
    fake_stream.__enter__ = MagicMock(return_value=fake_stream)
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_input_stream = mocker.patch(
        "tutor.audio.sd.InputStream",
        return_value=fake_stream,
    )

    fake_sf_write = mocker.patch("tutor.audio.sf.write")

    # simulate "press Enter twice" by replacing input()
    inputs = iter(["", ""])
    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: next(inputs))

    rec = AudioRecorder(sample_rate=16000, channels=1)
    out_path = tmp_path / "turn.wav"

    # inject a chunk into the recorder's callback so something gets written
    def fake_start():
        # call the audio callback once with fake data
        rec._on_audio(np.zeros((1600, 1), dtype=np.float32), 1600, None, None)
    fake_stream.start = fake_start

    result_path = rec.record_to_wav(out_path)

    assert result_path == out_path
    fake_input_stream.assert_called_once()
    fake_sf_write.assert_called_once()
    args, _ = fake_sf_write.call_args
    assert args[0] == str(out_path)
    assert args[2] == 16000  # sample rate
