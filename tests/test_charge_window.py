"""Tests for the best-time-to-charge calculator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from home_auto.engine.charge_window import (
    build_hourly_profile,
    find_cheapest_window,
    next_deadline,
    project_prices,
    recommend_charge_window,
)
from home_auto.models import PricePoint

TZ = ZoneInfo("America/Chicago")


def test_build_hourly_profile_averages_same_hour():
    base = datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc)  # 00:00 local (CDT)
    points = [
        PricePoint(base, 2.0),
        PricePoint(base + timedelta(minutes=5), 4.0),
    ]
    profile = build_hourly_profile(points, TZ)
    local_hour = base.astimezone(TZ).hour
    assert profile[local_hour] == 3.0


def test_next_deadline_rolls_to_tomorrow_when_past():
    now = datetime(2026, 6, 1, 18, 0, tzinfo=TZ)  # 6pm local
    deadline = next_deadline(now, deadline_hour=7, tz=TZ)
    assert deadline.hour == 7
    assert deadline.date() == (now + timedelta(days=1)).date()


def test_find_cheapest_window_picks_the_dip():
    start = datetime(2026, 6, 2, 0, 0, tzinfo=TZ)
    prices = [5, 5, 1, 1, 5, 5]  # cheap at hours 2-3
    forecast = [PricePoint(start + timedelta(hours=i), prices[i]) for i in range(6)]
    deadline = start + timedelta(hours=6)

    window = find_cheapest_window(forecast, session_hours=2, deadline=deadline)
    assert window is not None
    assert window.average_price_cents == 1.0
    assert window.start == start + timedelta(hours=2)
    assert window.duration_hours == 2.0


def test_find_cheapest_window_respects_deadline():
    start = datetime(2026, 6, 2, 0, 0, tzinfo=TZ)
    forecast = [PricePoint(start + timedelta(hours=i), 5) for i in range(6)]
    # Deadline only 1h out but a 2h session is required -> nothing fits.
    deadline = start + timedelta(hours=1)
    assert find_cheapest_window(forecast, session_hours=2, deadline=deadline) is None


def test_project_prices_uses_profile_by_hour():
    profile = {h: float(h) for h in range(24)}  # price == hour number
    start = datetime(2026, 6, 1, 22, 30, tzinfo=TZ)
    points = project_prices(profile, start, hours=3, tz=TZ)
    # First whole hour after 22:30 is 23:00.
    assert points[0].timestamp.astimezone(TZ).hour == 23
    assert points[0].price_cents == 23.0
    assert points[1].price_cents == 0.0  # midnight wraps to hour 0


def test_recommend_charge_window_end_to_end():
    # Build 3 days of history where the early-morning hours are cheapest.
    history: list[PricePoint] = []
    base = datetime(2026, 5, 29, 0, 0, tzinfo=TZ)
    for day in range(3):
        for hour in range(24):
            ts = (base + timedelta(days=day, hours=hour)).astimezone(timezone.utc)
            # Cheap 1-4am, pricey 5-8pm.
            price = 1.0 if 1 <= hour <= 4 else (12.0 if 17 <= hour <= 20 else 5.0)
            history.append(PricePoint(ts, price))

    now = datetime(2026, 6, 1, 22, 0, tzinfo=TZ)  # 10pm, deadline 7am
    window, forecast = recommend_charge_window(
        history, session_hours=3, deadline_hour=7, tz=TZ, now=now
    )
    assert window is not None
    assert forecast  # projection was produced
    # The recommended window should sit in the cheap pre-dawn block.
    assert 1 <= window.start.astimezone(TZ).hour <= 4
    assert window.average_price_cents < 5.0
