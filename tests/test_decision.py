"""Tests for price classification and the transition-only alerting monitor."""

from __future__ import annotations

from datetime import datetime, timezone

from home_auto.config import ThresholdConfig
from home_auto.engine.decision import PriceMonitor, classify
from home_auto.models import AlertLevel, PricePoint, PriceState

TH = ThresholdConfig(high_price_cents=10.0, low_price_cents=3.0)


def _pt(price: float) -> PricePoint:
    return PricePoint(timestamp=datetime.now(timezone.utc), price_cents=price)


def test_classify_buckets_including_boundaries():
    assert classify(2.0, TH) == PriceState.CHEAP
    assert classify(3.0, TH) == PriceState.CHEAP        # at low threshold -> cheap
    assert classify(5.0, TH) == PriceState.NORMAL
    assert classify(10.0, TH) == PriceState.EXPENSIVE   # at high threshold -> expensive
    assert classify(12.0, TH) == PriceState.EXPENSIVE


def test_first_reading_sets_baseline_without_alerting():
    monitor = PriceMonitor(TH)
    assert monitor.update(_pt(5.0)) is None
    assert monitor.state == PriceState.NORMAL


def test_alert_only_fires_on_state_change():
    monitor = PriceMonitor(TH)
    monitor.update(_pt(5.0))                 # baseline NORMAL, no alert

    high = monitor.update(_pt(12.0))         # NORMAL -> EXPENSIVE
    assert high is not None
    assert high.level == AlertLevel.WARNING

    assert monitor.update(_pt(13.0)) is None  # still EXPENSIVE -> no repeat

    cheap = monitor.update(_pt(1.5))          # EXPENSIVE -> CHEAP
    assert cheap is not None
    assert cheap.level == AlertLevel.INFO
    assert "charge" in cheap.message.lower()
