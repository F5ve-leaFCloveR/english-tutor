from unittest.mock import MagicMock


def test_tts_speak_invokes_say(mocker):
    from tutor.tts import MacSayTTS
    fake_run = mocker.patch("tutor.tts.subprocess.run")
    tts = MacSayTTS(voice="Samantha", rate=180)
    tts.speak("Hello, candidate.")
    fake_run.assert_called_once()
    args = fake_run.call_args[0][0]
    assert args[0] == "say"
    assert "-v" in args and "Samantha" in args
    assert "-r" in args and "180" in args
    assert "Hello, candidate." in args


def test_tts_speak_empty_text_is_noop(mocker):
    from tutor.tts import MacSayTTS
    fake_run = mocker.patch("tutor.tts.subprocess.run")
    tts = MacSayTTS()
    tts.speak("")
    tts.speak("   ")
    fake_run.assert_not_called()
