"""Downsample price history for the longer chart ranges.

The 1-week and 1-month chart views would be thousands of 5-minute points: slow
to send and an unreadable smear on screen. We collapse them to one averaged
point per clock hour, which keeps the Robinhood-style line smooth and fast while
preserving the daily shape.
"""

from __future__ import annotations

from datetime import datetime

from ..models import PricePoint


def _bucketed_averages(
    points: list[PricePoint], floor: "callable"
) -> list[PricePoint]:
    """Average points into buckets keyed by `floor(timestamp)`, oldest first.

    `floor` maps a timestamp to the start of its bucket (e.g. top of the hour or
    midnight). Input need not be sorted; output is sorted by time.
    """
    buckets: dict[datetime, list[float]] = {}
    for p in points:
        key = floor(p.timestamp)
        buckets.setdefault(key, []).append(p.price_cents)

    averaged = [
        PricePoint(timestamp=key, price_cents=sum(prices) / len(prices))
        for key, prices in buckets.items()
    ]
    averaged.sort(key=lambda p: p.timestamp)
    return averaged


def hourly_averages(points: list[PricePoint]) -> list[PricePoint]:
    """Average price points into one point per clock hour, oldest first.

    Used for the 1W/1M chart ranges. An empty input yields an empty list.
    """
    return _bucketed_averages(
        points, lambda ts: ts.replace(minute=0, second=0, microsecond=0)
    )


def daily_averages(points: list[PricePoint]) -> list[PricePoint]:
    """Average price points into one point per calendar day, oldest first.

    Used for the 1Y chart range, where a year of hourly points (~8,760) would be
    far too dense to read; one point per day (~365) keeps the trend legible.
    """
    return _bucketed_averages(
        points, lambda ts: ts.replace(hour=0, minute=0, second=0, microsecond=0)
    )
