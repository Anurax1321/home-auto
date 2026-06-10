"""Tests for the editable-settings store and its validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from home_auto.settings_store import SettingsStore, ThresholdSettings


def test_threshold_validation_rejects_low_above_high():
    with pytest.raises(ValidationError):
        ThresholdSettings(high_price_cents=3.0, low_price_cents=5.0)


def test_threshold_validation_rejects_nonpositive_high():
    with pytest.raises(ValidationError):
        ThresholdSettings(high_price_cents=0.0, low_price_cents=0.0)


def test_save_and_load_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    assert store.load_thresholds() is None  # nothing saved yet

    store.save_thresholds(ThresholdSettings(high_price_cents=12.5, low_price_cents=2.0))
    loaded = store.load_thresholds()
    assert loaded is not None
    assert loaded.high_price_cents == 12.5
    assert loaded.low_price_cents == 2.0


def test_corrupt_file_loads_as_none(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not valid json", encoding="utf-8")
    assert SettingsStore(path).load_thresholds() is None
