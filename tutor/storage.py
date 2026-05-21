"""JSON-file session persistence. One file per session, grouped by date."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


@dataclass
class SessionStorage:
    root: Path
    now: Callable[[], datetime] = datetime.now

    def _session_path(self, session_id: str, day: str) -> Path:
        return self.root / day / f"{session_id}.json"

    def _find_session_path(self, session_id: str) -> Path:
        matches = list(self.root.rglob(f"{session_id}.json"))
        if not matches:
            raise FileNotFoundError(f"No session file for id={session_id}")
        return matches[0]

    def _write(self, path: Path, data: dict) -> None:
        # Atomic against process crash, not against power loss (no fsync).
        # Acceptable for a single-user local CLI.
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(str(tmp), str(path))
        except Exception:
            # Clean up orphaned tmp on any failure during write.
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def create_session(self, scenario_id: str) -> str:
        now = self.now()
        day = now.date().isoformat()
        session_id = uuid.uuid4().hex[:12]
        path = self._session_path(session_id, day)
        self._write(path, {
            "session_id": session_id,
            "scenario_id": scenario_id,
            "started_at": now.isoformat(),
            "ended_at": None,
            "turns": [],
        })
        return session_id

    def append_turn(self, session_id: str, user_text: str, llm_text: str) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["turns"].append({
            "ts": self.now().isoformat(),
            "user_text": user_text,
            "llm_text": llm_text,
        })
        self._write(path, data)

    def end_session(self, session_id: str) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["ended_at"] = self.now().isoformat()
        self._write(path, data)

    def set_growth_points(self, session_id: str, growth_points: list[dict]) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["growth_points"] = growth_points
        self._write(path, data)

    def set_growth_points_error(self, session_id: str, error_message: str) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["growth_points_error"] = error_message
        self._write(path, data)

    def set_cards_created(self, session_id: str, card_ids: list[str]) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["cards_created"] = card_ids
        self._write(path, data)

    def load_session(self, session_id: str) -> dict:
        path = self._find_session_path(session_id)
        return json.loads(path.read_text())
