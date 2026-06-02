"""Best-time-to-charge calculator.

The honest problem: ComEd's public feed gives us *past and present* prices, not
a guaranteed future forecast. So to recommend when to charge tonight we build a
"typical day" profile from recent history (average price for each hour of the
day) and project it forward. As we accumulate more history this gets sharper;
if ComEd later exposes a day-ahead endpoint we can swap the projection out
without touching the window-search logic below.

Pipeline:
    build_hourly_profile()  -> {hour_of_day: average_cents} from history
    project_prices()        -> hourly PricePoints for the upcoming window
    find_cheapest_window()  -> the cheapest contiguous block that finishes
                               before the deadline
recommend_charge_window() chains all three for the caller.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..models import ChargeWindow, PricePoint


def build_hourly_profile(
    history: list[PricePoint], tz: ZoneInfo
) -> dict[int, float]:
    """Average the historical prices by local hour-of-day (0..23).

    Returns a dict mapping each hour we have data for to its mean price in
    cents/kWh. Hours with no data are simply absent.
    """
    sums: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for point in history:
        hour = point.timestamp.astimezone(tz).hour
        sums[hour] += point.price_cents
        counts[hour] += 1
    return {hour: sums[hour] / counts[hour] for hour in counts}


def next_deadline(now: datetime, deadline_hour: int, tz: ZoneInfo) -> datetime:
    """Return the next local datetime at `deadline_hour` strictly after `now`."""
    local_now = now.astimezone(tz)
    candidate = local_now.replace(
        hour=deadline_hour, minute=0, second=0, microsecond=0
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def project_prices(
    profile: dict[int, float],
    start: datetime,
    hours: int,
    tz: ZoneInfo,
) -> list[PricePoint]:
    """Project `hours` hourly prices forward from the next whole hour after `start`.

    Each projected point uses the profile's average for that hour-of-day. Hours
    missing from the profile fall back to the profile's overall mean (or 0 if
    the profile is empty, e.g. on the very first run with no history).
    """
    local_start = start.astimezone(tz)
    first_hour = local_start.replace(minute=0, second=0, microsecond=0)
    if first_hour < local_start:
        first_hour += timedelta(hours=1)

    fallback = sum(profile.values()) / len(profile) if profile else 0.0

    points: list[PricePoint] = []
    for i in range(hours):
        ts = first_hour + timedelta(hours=i)
        price = profile.get(ts.hour, fallback)
        points.append(PricePoint(timestamp=ts, price_cents=price))
    return points


def find_cheapest_window(
    forecast: list[PricePoint],
    session_hours: float,
    deadline: datetime,
) -> ChargeWindow | None:
    """Find the cheapest contiguous block that fits before the deadline.

    `forecast` is a list of hourly PricePoints (each treated as covering one
    hour). We need `ceil(session_hours)` consecutive hours whose end is at or
    before `deadline`, and pick the block with the lowest average price.
    Returns None if no block long enough fits before the deadline.
    """
    slots = max(1, math.ceil(session_hours))
    ordered = sorted(forecast, key=lambda p: p.timestamp)

    best: ChargeWindow | None = None
    # Slide a window of `slots` consecutive hourly points across the forecast.
    for i in range(len(ordered) - slots + 1):
        window = ordered[i : i + slots]
        start = window[0].timestamp
        end = window[-1].timestamp + timedelta(hours=1)  # last slot covers 1h
        if end > deadline:
            continue  # would not finish in time
        average = sum(p.price_cents for p in window) / slots
        if best is None or average < best.average_price_cents:
            best = ChargeWindow(start=start, end=end, average_price_cents=average)
    return best


def recommend_charge_window(
    history: list[PricePoint],
    session_hours: float,
    deadline_hour: int,
    tz: ZoneInfo,
    now: datetime,
) -> tuple[ChargeWindow | None, list[PricePoint]]:
    """High-level helper: profile history, project to the deadline, find the window.

    Returns a tuple of (recommended window or None, the projected forecast) so
    the caller can both act on the recommendation and display the projection.
    """
    profile = build_hourly_profile(history, tz)
    deadline = next_deadline(now, deadline_hour, tz)

    # Project from the next whole hour up to the deadline (cap at 24h of slots).
    local_now = now.astimezone(tz)
    hours_until_deadline = math.ceil(
        (deadline - local_now).total_seconds() / 3600.0
    )
    hours = max(0, min(24, hours_until_deadline))

    forecast = project_prices(profile, now, hours, tz)
    window = find_cheapest_window(forecast, session_hours, deadline)
    return window, forecast
