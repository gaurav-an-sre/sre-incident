"""Persist typed SDK events as an auditable JSONL stream."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _payload(event: Any) -> dict[str, Any]:
    if isinstance(event, Mapping):
        return dict(event)
    if dataclasses.is_dataclass(event):
        return dataclasses.asdict(event)  # type: ignore[arg-type]
    if hasattr(event, "__dict__"):
        return {
            key: value
            for key, value in vars(event).items()
            if not key.startswith("_")
        }
    return {"value": str(event)}


def _event_type(event: Any, payload: dict[str, Any]) -> str:
    return str(payload.get("type") or getattr(event, "type", type(event).__name__))


def _event_timestamp(event: Any, payload: dict[str, Any]) -> str:
    timestamp = payload.get("timestamp") or getattr(event, "timestamp", None)
    timestamp = timestamp or payload.get("created_at") or getattr(event, "created_at", None)
    if timestamp is not None:
        return str(timestamp)
    return datetime.now(UTC).isoformat()


def stream_run(run: Any, destination: Path) -> Any:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as output:
        for event in run.stream():
            payload = _payload(event)
            output.write(
                json.dumps(
                    {
                        "event_type": _event_type(event, payload),
                        "timestamp": _event_timestamp(event, payload),
                        "payload": payload,
                    },
                    default=str,
                    sort_keys=True,
                )
                + "\n"
            )
    return run.wait()
