"""Runtime-editable settings, persisted to data/settings.json.

Right now the only live-editable settings are the price thresholds (the
cheap/expensive cutoffs). config.yaml provides the startup defaults; if the user
changes the thresholds from the dashboard we save them here and load them back
over the defaults on the next start.

Everything is validated by pydantic, so a bad value from the API is rejected
before it ever touches the running service or the saved file.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from .storage import data_dir, read_json, write_json

# File name within the data directory.
_SETTINGS_FILE = "settings.json"


class ThresholdSettings(BaseModel):
    """The cheap/expensive price cutoffs, in cents/kWh.

    Range-limited so an obviously wrong value (negative, or absurdly high) is
    rejected, and low must not exceed high or classification would be nonsense.
    """

    high_price_cents: float = Field(gt=0, le=100)
    low_price_cents: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _low_not_above_high(self) -> "ThresholdSettings":
        if self.low_price_cents > self.high_price_cents:
            raise ValueError("low_price_cents must not exceed high_price_cents")
        return self


class SettingsStore:
    """Loads/saves the editable-settings JSON file.

    Pass an explicit path in tests; production uses `default()` which points at
    data/settings.json (honoring HOME_AUTO_DATA_DIR).
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    def default(cls) -> "SettingsStore":
        return cls(data_dir() / _SETTINGS_FILE)

    def load_thresholds(self) -> ThresholdSettings | None:
        """Return saved threshold overrides, or None if absent/invalid."""
        raw = read_json(self._path)
        if not isinstance(raw, dict):
            return None
        thresholds = raw.get("thresholds")
        if not isinstance(thresholds, dict):
            return None
        try:
            return ThresholdSettings(**thresholds)
        except Exception:  # noqa: BLE001 - ignore a corrupt override, use defaults
            return None

    def save_thresholds(self, thresholds: ThresholdSettings) -> None:
        """Persist threshold overrides, merging into any existing settings."""
        raw = read_json(self._path)
        data = raw if isinstance(raw, dict) else {}
        data["thresholds"] = thresholds.model_dump()
        write_json(self._path, data)
