"""User-defined triggers: "when <metric> <operator> <value>, do <action>".

A trigger is a small rule the user creates from the dashboard, e.g. "when the
price drops below 2.5 c/kWh, push me a notification". Today the only action is
sending a notification, but the `action.type` field is deliberately a stub so
later phases (Tesla charging, thermostat, smart plugs) can add new action types
without changing the storage format.

Triggers are stored as JSON in data/triggers.json. Each one gets a server-side
id; clients never choose ids or file paths, so there is no path-traversal or
id-collision surface from the API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .storage import data_dir, read_json, write_json

# File name within the data directory.
_TRIGGERS_FILE = "triggers.json"

# Upper bound on stored triggers, so a misbehaving client can't grow the file
# without limit. Far above any realistic number of home rules.
_MAX_TRIGGERS = 100

# Which live value a trigger watches.
Metric = Literal["price", "hour_average"]
# Comparison applied between the metric and the trigger's value.
Operator = Literal["<", "<=", ">", ">="]
# The notification channels a trigger may target (the known channel names).
ChannelName = Literal["dashboard", "ntfy", "email"]


class TriggerAction(BaseModel):
    """What happens when a trigger fires.

    `type` is "notify" for now; future phases add e.g. "tesla_charge". `channels`
    is an optional allow-list of notification channel names; empty means "all
    enabled channels". `message` optionally overrides the default alert text.
    Fields are length-bounded so a direct API client can't store oversized data.
    """

    type: Literal["notify"] = "notify"
    channels: list[ChannelName] = Field(default_factory=list, max_length=10)
    message: str = Field(default="", max_length=500)


class TriggerCreate(BaseModel):
    """Fields a client supplies to create or replace a trigger (no id)."""

    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    metric: Metric = "price"
    operator: Operator
    value: float = Field(ge=-100, le=1000)
    action: TriggerAction = Field(default_factory=TriggerAction)
    # Minimum minutes between firings, so a trigger can't spam every poll.
    cooldown_minutes: int = Field(default=60, ge=0, le=10080)


class Trigger(TriggerCreate):
    """A stored trigger: a TriggerCreate plus its server-assigned id."""

    id: str


class TriggerStore:
    """Loads/saves the list of triggers in data/triggers.json.

    Ids are generated here from a monotonic counter persisted alongside the
    triggers, so they never collide and never come from the client.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    def default(cls) -> "TriggerStore":
        return cls(data_dir() / _TRIGGERS_FILE)

    def _read_raw(self) -> dict:
        raw = read_json(self._path)
        if not isinstance(raw, dict):
            return {"next_id": 1, "triggers": []}
        raw.setdefault("next_id", 1)
        raw.setdefault("triggers", [])
        return raw

    def list(self) -> list[Trigger]:
        """Return all stored triggers (silently skipping any corrupt entries)."""
        triggers: list[Trigger] = []
        for entry in self._read_raw()["triggers"]:
            try:
                triggers.append(Trigger(**entry))
            except Exception:  # noqa: BLE001 - ignore a bad row, keep the rest
                continue
        return triggers

    def get(self, trigger_id: str) -> Trigger | None:
        for t in self.list():
            if t.id == trigger_id:
                return t
        return None

    def add(self, data: TriggerCreate) -> Trigger:
        """Create a new trigger with a fresh server-assigned id.

        Raises ValueError if the trigger limit is reached, so the API can turn
        it into a clean 400 instead of growing the file unbounded.
        """
        raw = self._read_raw()
        if len(raw["triggers"]) >= _MAX_TRIGGERS:
            raise ValueError(f"trigger limit reached ({_MAX_TRIGGERS})")
        trigger_id = str(raw["next_id"])
        raw["next_id"] = raw["next_id"] + 1
        trigger = Trigger(id=trigger_id, **data.model_dump())
        raw["triggers"].append(trigger.model_dump())
        write_json(self._path, raw)
        return trigger

    def update(self, trigger_id: str, data: TriggerCreate) -> Trigger | None:
        """Replace an existing trigger's fields; return None if id is unknown."""
        raw = self._read_raw()
        for i, entry in enumerate(raw["triggers"]):
            if entry.get("id") == trigger_id:
                trigger = Trigger(id=trigger_id, **data.model_dump())
                raw["triggers"][i] = trigger.model_dump()
                write_json(self._path, raw)
                return trigger
        return None

    def delete(self, trigger_id: str) -> bool:
        """Remove a trigger; return True if one was removed."""
        raw = self._read_raw()
        before = len(raw["triggers"])
        raw["triggers"] = [
            e for e in raw["triggers"] if e.get("id") != trigger_id
        ]
        if len(raw["triggers"]) == before:
            return False
        write_json(self._path, raw)
        return True
