"""Minimal local persistence for the fixed fixture demo watchlist.

This is deliberately not a real account system.  It stores one demo user's
watch entries in a JSON file, isolated from any production data, and keeps
the first-follow snapshot immutable.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEMO_USER = "fixture-user"
STORE_VERSION = 1
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(LOCAL_ZONE).replace(tzinfo=None, microsecond=0).isoformat()


@dataclass
class WatchEntry:
    watch_id: str
    user: str
    security_id: str
    strategy_id: str
    scenario: str
    style: str
    batch_id: str
    created_at: str
    snapshot: dict[str, Any]
    status: str = "ACTIVE"
    removed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "watch_id": self.watch_id,
            "user": self.user,
            "security_id": self.security_id,
            "strategy_id": self.strategy_id,
            "scenario": self.scenario,
            "style": self.style,
            "batch_id": self.batch_id,
            "created_at": self.created_at,
            "snapshot": self.snapshot,
            "status": self.status,
            "removed_at": self.removed_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WatchEntry":
        return cls(
            watch_id=str(payload["watch_id"]),
            user=str(payload.get("user", DEMO_USER)),
            security_id=str(payload["security_id"]),
            strategy_id=str(payload["strategy_id"]),
            scenario=str(payload["scenario"]),
            style=str(payload.get("style", "BALANCED/1")),
            batch_id=str(payload["batch_id"]),
            created_at=str(payload["created_at"]),
            snapshot=dict(payload["snapshot"]),
            status=str(payload.get("status", "ACTIVE")),
            removed_at=payload.get("removed_at"),
        )


class WatchStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": STORE_VERSION, "user": DEMO_USER, "entries": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": STORE_VERSION, "user": DEMO_USER, "entries": []}
        if not isinstance(payload, dict):
            return {"version": STORE_VERSION, "user": DEMO_USER, "entries": []}
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            entries = []
        return {
            "version": STORE_VERSION,
            "user": str(payload.get("user", DEMO_USER)),
            "entries": [item for item in entries if isinstance(item, dict)],
        }

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def entries(self) -> list[WatchEntry]:
        with self._lock:
            payload = self._read()
        return [WatchEntry.from_dict(item) for item in payload["entries"]]

    def get(self, watch_id: str) -> WatchEntry | None:
        for entry in self.entries():
            if entry.watch_id == watch_id:
                return entry
        return None

    def add(
        self,
        *,
        security_id: str,
        strategy_id: str,
        scenario: str,
        style: str,
        batch_id: str,
        snapshot: dict[str, Any],
    ) -> WatchEntry:
        with self._lock:
            payload = self._read()
            for item in payload["entries"]:
                if (
                    item.get("status") == "ACTIVE"
                    and item.get("security_id") == security_id
                    and item.get("strategy_id") == strategy_id
                    and item.get("scenario") == scenario
                ):
                    return WatchEntry.from_dict(item)
            entry = WatchEntry(
                watch_id=f"w-{uuid.uuid4().hex[:12]}",
                user=DEMO_USER,
                security_id=security_id,
                strategy_id=strategy_id,
                scenario=scenario,
                style=style,
                batch_id=batch_id,
                created_at=_now(),
                snapshot=snapshot,
            )
            payload["entries"].append(entry.to_dict())
            self._write(payload)
            return entry

    def remove(self, watch_id: str) -> WatchEntry | None:
        with self._lock:
            payload = self._read()
            for item in payload["entries"]:
                if item.get("watch_id") == watch_id:
                    if item.get("status") == "ACTIVE":
                        item["status"] = "REMOVED"
                        item["removed_at"] = _now()
                        self._write(payload)
                    return WatchEntry.from_dict(item)
        return None
