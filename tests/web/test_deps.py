def test_dependencies_dataclass_holds_components(tmp_path, monkeypatch):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.asr import WhisperASR
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine
    from tutor.llm import LLMClient
    from unittest.mock import MagicMock

    deps = Dependencies(
        budget=BudgetTracker(path=tmp_path/"b.json", daily_usd_cap=1.0,
                              daily_token_cap=1_000_000),
        llm=MagicMock(spec=LLMClient),
        asr=MagicMock(spec=WhisperASR),
        storage=SessionStorage(root=tmp_path/"sessions"),
        srs=SRSEngine(path=tmp_path/"cards.json"),
        evaluator_model="m1",
        grader_model="m2",
    )
    assert deps.budget is not None
    assert deps.evaluator_model == "m1"


def test_build_dependencies_from_settings(tmp_path, monkeypatch, mocker):
    """build_dependencies wires up real objects from settings + project_root."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    mocker.patch("tutor.web.deps.WhisperASR")  # avoid real model load

    from tutor.web.deps import build_dependencies
    deps = build_dependencies(project_root=tmp_path)
    assert deps.budget is not None
    assert deps.llm is not None
    assert deps.storage is not None
    assert deps.srs is not None
    assert deps.evaluator_model == "google/gemini-2.5-pro"
    assert deps.grader_model == "google/gemini-2.5-flash"
