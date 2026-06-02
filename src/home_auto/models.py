"""Shared data models used across the whole service.

These are plain, immutable-ish dataclasses so they are trivial to construct in
tests and to serialize for the dashboard. Heavier validation (config parsing)
lives in config.py using pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class PricePoint:
    """A single electricity price reading.

    Attributes:
        timestamp: When the price applies, as a timezone-aware UTC datetime.
        price_cents: Price in US cents per kWh (ComEd energy-supply rate).
    """

    timestamp: datetime
    price_cents: float


class PriceState(str, Enum):
    """Where the current price sits relative to the configured thresholds."""

    CHEAP = "cheap"          # at/below low_price_cents -> good time to run loads
    NORMAL = "normal"        # in between
    EXPENSIVE = "expensive"  # at/above high_price_cents -> hold off on big loads


@dataclass(frozen=True)
class ChargeWindow:
    """A recommended contiguous window to run a high-power load (e.g. charge the car).

    Attributes:
        start: Window start (timezone-aware).
        end: Window end (timezone-aware).
        average_price_cents: Mean projected price across the window.
    """

    start: datetime
    end: datetime
    average_price_cents: float

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


class AlertLevel(str, Enum):
    """Severity used to style/route notifications."""

    INFO = "info"
    WARNING = "warning"


@dataclass(frozen=True)
class Alert:
    """A single notification to deliver through the enabled channels."""

    level: AlertLevel
    title: str
    message: str
    created_at: datetime


@dataclass
class WeatherForecastPeriod:
    """One period of the NWS forecast (NWS returns ~12-hour day/night periods)."""

    name: str                 # e.g. "This Afternoon", "Tonight"
    start: datetime
    temperature: float        # in temperature_unit
    temperature_unit: str     # "F" or "C"
    short_forecast: str       # e.g. "Sunny", "Chance Rain Showers"


@dataclass
class WeatherForecast:
    """The processed forecast we hand to the rest of the app."""

    periods: list[WeatherForecastPeriod] = field(default_factory=list)

    @property
    def current(self) -> WeatherForecastPeriod | None:
        """The nearest/active forecast period, if any."""
        return self.periods[0] if self.periods else None
