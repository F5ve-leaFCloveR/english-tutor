import pytest
from pathlib import Path


def test_cli_unknown_scenario_exits_2_with_friendly_message(monkeypatch, capsys):
    """Regression: bad --scenario should NOT crash with a traceback."""
    from tutor.cli import main
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    exit_code = main(["interview", "--scenario", "does_not_exist"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "does_not_exist" in (captured.err + captured.out)
    assert "Traceback" not in (captured.err + captured.out)
