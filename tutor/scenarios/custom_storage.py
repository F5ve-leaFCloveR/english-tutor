"""User-defined scenarios persisted as a single JSON file."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from tutor.scenarios.loader import ScenarioNotFoundError

log = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """ASCII-lowercase, hyphenated; strip non-alphanumerics."""
    out = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return out or "scenario"


@dataclass
class CustomScenarioStorage:
    path: Path
    now: Callable[[], datetime] = field(default=datetime.now)

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {"scenarios": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            backup = self.path.with_suffix(self.path.suffix + f".broken-{int(time.time())}")
            try:
                self.path.rename(backup)
            except OSError:
                pass
            log.warning("custom_scenarios.json corrupt; backed up to %s; using empty list. %s", backup, e)
            return {"scenarios": []}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(str(tmp), str(self.path))
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def list_all(self) -> list[dict]:
        data = self._load_raw()
        scenarios = list(data.get("scenarios", []))
        scenarios.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return scenarios

    def load(self, scenario_id: str) -> dict:
        for s in self.list_all():
            if s.get("id") == scenario_id:
                return s
        raise ScenarioNotFoundError(f"No custom scenario with id={scenario_id}")

    def create(
        self,
        name: str,
        difficulty: str,
        system_prompt: str,
        opening_line: str,
    ) -> dict:
        data = self._load_raw()
        existing_ids = {s.get("id") for s in data.get("scenarios", [])}
        base = _slugify(name)
        new_id = base
        n = 2
        while new_id in existing_ids:
            new_id = f"{base}-{n}"
            n += 1
        entry = {
            "id": new_id,
            "name": name,
            "difficulty": difficulty,
            "system_prompt": system_prompt,
            "opening_line": opening_line,
            "created_at": self.now().isoformat(),
        }
        data.setdefault("scenarios", []).append(entry)
        self._write(data)
        return entry

    def delete(self, scenario_id: str) -> None:
        data = self._load_raw()
        before = data.get("scenarios", [])
        after = [s for s in before if s.get("id") != scenario_id]
        if len(after) == len(before):
            raise ScenarioNotFoundError(f"No custom scenario with id={scenario_id}")
        data["scenarios"] = after
        self._write(data)
