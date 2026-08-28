"""Durable orchestration state."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, cast


class StateStore:
    def __init__(self, root: Path, incident_id: str, *, fresh: bool = False) -> None:
        self.path = root / "out" / incident_id / "state.json"
        self._lock = threading.Lock()
        if fresh or not self.path.exists():
            self.data: dict[str, Any] = {
                "incident_id": incident_id,
                "roles": {},
                "adjudication": None,
            }
        else:
            self.data = cast(
                dict[str, Any], json.loads(self.path.read_text(encoding="utf-8"))
            )

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary.replace(self.path)

    def role(self, role: str) -> dict[str, Any]:
        value = self.data.setdefault("roles", {}).setdefault(role, {})
        value.setdefault("agent_id", None)
        value.setdefault("status", "pending")
        value.setdefault("report", None)
        value.setdefault("validation", None)
        value.setdefault("run_ids", [])
        value.setdefault(
            "stream_path", f"out/{self.data['incident_id']}/{role}.jsonl"
        )
        return cast(dict[str, Any], value)
