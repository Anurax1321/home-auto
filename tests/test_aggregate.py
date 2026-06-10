"""Tests for hourly downsampling of price history."""

from __future__ import annotations

from datetime import datetime, timezone

from home_auto.engine.aggregate import daily_averages, hourly_averages
from home_auto.models import PricePoint


def _p(hour: int, minute: int, price: float) -> PricePoint:
    return PricePoint(
        timestamp=datetime(2026, 6, 1, hour, minute, tzinfo=timezone.utc),
        price_cents=price,
    )


def test_empty_input():
    assert hourly_averages([]) == []


def test_averages_within_each_hour_and_sorts():
    points = [
        _p(9, 0, 2.0),
        _p(9, 30, 4.0),   # hour 9 -> avg 3.0
        _p(8, 15, 5.0),   # hour 8 -> avg 5.0 (out of order on purpose)
    ]
    result = hourly_averages(points)
    assert [p.timestamp.hour for p in result] == [8, 9]  # sorted oldest first
    assert result[0].price_cents == 5.0
    assert result[1].price_cents == 3.0
    # Bucket timestamps are zeroed to the top of the hour.
    assert result[1].timestamp.minute == 0


def test_daily_averages_buckets_by_day():
    points = [
        PricePoint(datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc), 2.0),
        PricePoint(datetime(2026, 6, 1, 21, 0, tzinfo=timezone.utc), 6.0),  # day 1 -> 4.0
        PricePoint(datetime(2026, 6, 2, 3, 0, tzinfo=timezone.utc), 1.0),   # day 2 -> 1.0
    ]
    result = daily_averages(points)
    assert [p.timestamp.day for p in result] == [1, 2]
    assert result[0].price_cents == 4.0
    assert result[1].price_cents == 1.0
    # Bucket timestamps are zeroed to midnight.
    assert result[0].timestamp.hour == 0 and result[0].timestamp.minute == 0
