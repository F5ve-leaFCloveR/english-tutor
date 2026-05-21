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


def test_cli_review_help_works(monkeypatch, capsys):
    from tutor.cli import main
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    with pytest.raises(SystemExit) as exc_info:
        main(["review", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "review" in captured.out.lower()
    assert "--limit" in captured.out
    assert "--tag" in captured.out


def test_cli_review_no_due_cards(monkeypatch, tmp_path, capsys, mocker):
    """Smoke: review with no due cards prints message and exits 0."""
    from tutor.cli import main
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    monkeypatch.chdir(tmp_path)
    from tutor import cli as cli_mod
    mocker.patch.object(cli_mod, "_project_root", return_value=tmp_path)

    exit_code = main(["review"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No cards due" in captured.out
