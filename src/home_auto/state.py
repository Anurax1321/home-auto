"""In-memory snapshot of the latest computed state.

The polling loop writes a fresh Snapshot each cycle; the web dashboard reads it.
Keeping a single mutable container (rather than threading values everywhere)
makes the data flow easy to follow: producers set fields, the UI reads them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import ChargeWindow, PricePoint, PriceState, WeatherForecast


@dataclass
class Snapshot:
    """Everything the dashboard needs to render the current situation."""

    updated_at: datetime | None = None
    latest_price: PricePoint | None = None
    price_state: PriceState | None = None
    current_hour_average: float | None = None

    # Last ~24h of 5-minute prices, for the dashboard graph (oldest first).
    recent_prices: list[PricePoint] = field(default_factory=list)

    # Projected hourly prices used to pick the charge window (oldest first).
    forecast: list[PricePoint] = field(default_factory=list)

    # Recommended cheapest upcoming charge window (None if none fits).
    charge_window: ChargeWindow | None = None

    weather: WeatherForecast | None = None

    # Human-readable description of the most recent poll failure, if any.
    last_error: str | None = None
