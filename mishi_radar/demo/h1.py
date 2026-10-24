"""Independent local persistence for the fixed-fixture H1 observation book.

H1 is deliberately separate from the F5 watchlist.  It stores one demo user's
manual observations in its own JSON file, keeps every corrected version, and
never mutates the F5 store.  It is not a broker position, trade ledger or
account system.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEMO_USER = "fixture-user"
H1_STORE_VERSION = 1
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(LOCAL_ZONE).replace(tzinfo=None, microsecond=0).isoformat()


@dataclass(frozen=True)
class H1Version:
    version: int
    security_id: str
    strategy_id: str | None
    quantity: str
    average_cost: str
    cost_basis_date: str
    note: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "security_id": self.security_id,
            "strategy_id": self.strategy_id,
            "quantity": self.quantity,
            "average_cost": self.average_cost,
            "cost_basis_date": self.cost_basis_date,
            "note": self.note,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> H1Version:
        strategy_id = payload.get("strategy_id")
        note = payload.get("note")
        return cls(
            version=int(payload["version"]),
            security_id=str(payload["security_id"]),
            strategy_id=str(strategy_id) if strategy_id else None,
            quantity=str(payload["quantity"]),
            average_cost=str(payload["average_cost"]),
            cost_basis_date=str(payload["cost_basis_date"]),
            note=str(note) if note else None,
            created_at=str(payload["created_at"]),
        )


@dataclass
class H1Observation:
    observation_id: str
    user: str
    scenario: str
    created_at: str
    versions: list[H1Version] = field(default_factory=list)
    status: str = "ACTIVE"
    ended_at: str | None = None
    end_reason: str | None = None
    end_snapshot: dict[str, Any] | None = None

    @property
    def current_version(self) -> H1Version:
        return self.versions[-1]

    @property
    def version_count(self) -> int:
        return len(self.versions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "user": self.user,
            "scenario": self.scenario,
            "created_at": self.created_at,
            "versions": [item.to_dict() for item in self.versions],
            "status": self.status,
            "ended_at": self.ended_at,
            "end_reason": self.end_reason,
            "end_snapshot": self.end_snapshot,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> H1Observation:
        versions = [
            H1Version.from_dict(item)
            for item in payload.get("versions", [])
            if isinstance(item, dict)
        ]
        if not versions:
            raise ValueError("H1 observation requires at least one version")
        end_snapshot = payload.get("end_snapshot")
        return cls(
            observation_id=str(payload["observation_id"]),
            user=str(payload.get("user", DEMO_USER)),
            scenario=str(payload["scenario"]),
            created_at=str(payload["created_at"]),
            versions=versions,
            status=str(payload.get("status", "ACTIVE")),
            ended_at=payload.get("ended_at"),
            end_reason=payload.get("end_reason"),
            end_snapshot=dict(end_snapshot) if isinstance(end_snapshot, dict) else None,
        )


class H1NotFound(KeyError):
    pass


class H1StateError(ValueError):
    pass


class H1Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": H1_STORE_VERSION, "user": DEMO_USER, "observations": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": H1_STORE_VERSION, "user": DEMO_USER, "observations": []}
        if not isinstance(payload, dict):
            return {"version": H1_STORE_VERSION, "user": DEMO_USER, "observations": []}
        observations = payload.get("observations", [])
        if not isinstance(observations, list):
            observations = []
        return {
            "version": H1_STORE_VERSION,
            "user": str(payload.get("user", DEMO_USER)),
            "observations": [item for item in observations if isinstance(item, dict)],
        }

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def observations(self) -> list[H1Observation]:
        with self._lock:
            payload = self._read()
        result: list[H1Observation] = []
        for item in payload["observations"]:
            try:
                result.append(H1Observation.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def get(self, observation_id: str) -> H1Observation | None:
        for observation in self.observations():
            if observation.observation_id == observation_id:
                return observation
        return None

    def create(
        self,
        *,
        scenario: str,
        security_id: str,
        strategy_id: str | None,
        quantity: str,
        average_cost: str,
        cost_basis_date: str,
        note: str | None,
    ) -> H1Observation:
        with self._lock:
            payload = self._read()
            created_at = _now()
            observation = H1Observation(
                observation_id=f"h1-{uuid.uuid4().hex[:12]}",
                user=DEMO_USER,
                scenario=scenario,
                created_at=created_at,
                versions=[
                    H1Version(
                        version=1,
                        security_id=security_id,
                        strategy_id=strategy_id,
                        quantity=quantity,
                        average_cost=average_cost,
                        cost_basis_date=cost_basis_date,
                        note=note,
                        created_at=created_at,
                    )
                ],
            )
            payload["observations"].append(observation.to_dict())
            self._write(payload)
            return observation

    def correct(
        self,
        observation_id: str,
        *,
        security_id: str,
        strategy_id: str | None,
        quantity: str,
        average_cost: str,
        cost_basis_date: str,
        note: str | None,
    ) -> H1Observation:
        with self._lock:
            payload = self._read()
            for item in payload["observations"]:
                if item.get("observation_id") != observation_id:
                    continue
                observation = H1Observation.from_dict(item)
                if observation.status != "ACTIVE":
                    raise H1StateError("ENDED_OBSERVATION_IS_READ_ONLY")
                created_at = _now()
                observation.versions.append(
                    H1Version(
                        version=observation.current_version.version + 1,
                        security_id=security_id,
                        strategy_id=strategy_id,
                        quantity=quantity,
                        average_cost=average_cost,
                        cost_basis_date=cost_basis_date,
                        note=note,
                        created_at=created_at,
                    )
                )
                item.clear()
                item.update(observation.to_dict())
                self._write(payload)
                return observation
        raise H1NotFound(observation_id)

    def end(
        self,
        observation_id: str,
        *,
        reason: str,
        snapshot: dict[str, Any],
    ) -> H1Observation:
        with self._lock:
            payload = self._read()
            for item in payload["observations"]:
                if item.get("observation_id") != observation_id:
                    continue
                observation = H1Observation.from_dict(item)
                if observation.status != "ACTIVE":
                    raise H1StateError("ENDED_OBSERVATION_IS_READ_ONLY")
                ended_at = _now()
                saved = dict(snapshot)
                saved["reason"] = reason
                saved["ended_at"] = ended_at
                observation.status = "ENDED"
                observation.ended_at = ended_at
                observation.end_reason = reason
                observation.end_snapshot = saved
                item.clear()
                item.update(observation.to_dict())
                self._write(payload)
                return observation
        raise H1NotFound(observation_id)
