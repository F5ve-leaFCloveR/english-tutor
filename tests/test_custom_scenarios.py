from datetime import datetime
from pathlib import Path
import json
import pytest


def test_create_returns_dict_with_id_and_timestamps(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json", now=lambda: datetime(2026, 5, 22, 12, 0))
    out = storage.create(
        name="My restaurant chat",
        difficulty="intermediate",
        system_prompt="You are a waiter...",
        opening_line="Welcome!",
    )
    assert out["id"] == "my-restaurant-chat"
    assert out["name"] == "My restaurant chat"
    assert out["difficulty"] == "intermediate"
    assert out["system_prompt"] == "You are a waiter..."
    assert out["opening_line"] == "Welcome!"
    assert out["created_at"] == "2026-05-22T12:00:00"


def test_create_writes_to_storage_file(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    p = tmp_path / "custom.json"
    storage = CustomScenarioStorage(path=p)
    storage.create(name="X", difficulty="easy", system_prompt="...", opening_line="")
    data = json.loads(p.read_text())
    assert len(data["scenarios"]) == 1
    assert data["scenarios"][0]["id"] == "x"


def test_create_collision_appends_suffix(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    s1 = storage.create(name="Talk", difficulty="easy", system_prompt="A", opening_line="")
    s2 = storage.create(name="Talk", difficulty="easy", system_prompt="B", opening_line="")
    s3 = storage.create(name="Talk", difficulty="easy", system_prompt="C", opening_line="")
    assert s1["id"] == "talk"
    assert s2["id"] == "talk-2"
    assert s3["id"] == "talk-3"


def test_list_all_returns_sorted_by_created_at_desc(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    times = [datetime(2026, 5, 22, h, 0) for h in (10, 12, 11)]
    it = iter(times)
    storage = CustomScenarioStorage(path=tmp_path / "custom.json", now=lambda: next(it))
    storage.create(name="A", difficulty="easy", system_prompt="...", opening_line="")
    storage.create(name="B", difficulty="easy", system_prompt="...", opening_line="")
    storage.create(name="C", difficulty="easy", system_prompt="...", opening_line="")
    out = storage.list_all()
    names = [s["name"] for s in out]
    assert names == ["B", "C", "A"]  # 12h, 11h, 10h


def test_load_returns_existing(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    created = storage.create(name="My Talk", difficulty="advanced", system_prompt="P", opening_line="O")
    loaded = storage.load(created["id"])
    assert loaded["system_prompt"] == "P"


def test_load_missing_raises(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    from tutor.scenarios.loader import ScenarioNotFoundError
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    with pytest.raises(ScenarioNotFoundError):
        storage.load("nonexistent")


def test_delete_removes_and_persists(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    p = tmp_path / "custom.json"
    storage = CustomScenarioStorage(path=p)
    s = storage.create(name="Talk", difficulty="easy", system_prompt="A", opening_line="")
    storage.delete(s["id"])
    assert storage.list_all() == []
    data = json.loads(p.read_text())
    assert data["scenarios"] == []


def test_delete_missing_raises(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    from tutor.scenarios.loader import ScenarioNotFoundError
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    with pytest.raises(ScenarioNotFoundError):
        storage.delete("missing")


def test_empty_file_treated_as_empty(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "missing.json")
    assert storage.list_all() == []


def test_corrupt_file_backed_up(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    p = tmp_path / "custom.json"
    p.write_text("{ this is not valid json")
    storage = CustomScenarioStorage(path=p)
    assert storage.list_all() == []
    # corrupt file moved aside
    backups = list(tmp_path.glob("custom.json.broken-*"))
    assert len(backups) == 1
