"""Client for the US National Weather Service forecast API (api.weather.gov).

NWS is free, needs no API key, and covers the whole US (perfect for ComEd's
Illinois territory). It requires a descriptive User-Agent header identifying
the app, which we set on every request.

Fetching a forecast is a two-step dance:
    1. GET /points/{lat},{lon}  -> tells us the forecast URL for that grid cell.
    2. GET <that forecast URL>  -> the actual day/night forecast periods.
The points->forecast mapping is stable for a location, so we cache step 1.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from ..models import WeatherForecast, WeatherForecastPeriod

API_BASE = "https://api.weather.gov"

# NWS asks for a User-Agent that identifies the application and a contact.
DEFAULT_USER_AGENT = "home-auto/0.1 (personal home automation project)"


class WeatherClient:
    """Async client for the NWS forecast API.

    Args:
        http: an httpx.AsyncClient (caller owns its lifecycle).
        latitude, longitude: the location to forecast.
        user_agent: identifying string required by NWS.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        latitude: float,
        longitude: float,
        user_agent: str = DEFAULT_USER_AGENT,
        base_url: str = API_BASE,
    ) -> None:
        self._http = http
        self._lat = latitude
        self._lon = longitude
        self._base_url = base_url
        self._headers = {"User-Agent": user_agent, "Accept": "application/geo+json"}
        # Cache the resolved forecast URL so we only resolve the grid cell once.
        self._forecast_url: str | None = None

    async def _resolve_forecast_url(self) -> str:
        """Look up (and cache) the forecast URL for our coordinates."""
        if self._forecast_url is not None:
            return self._forecast_url

        # NWS rounds coordinates to 4 decimals; doing it ourselves avoids a redirect.
        point = f"{self._lat:.4f},{self._lon:.4f}"
        resp = await self._http.get(
            f"{self._base_url}/points/{point}", headers=self._headers
        )
        resp.raise_for_status()

        forecast_url = resp.json()["properties"]["forecast"]
        # Defense-in-depth: only ever fetch a forecast URL that points back at
        # the NWS API. This prevents a spoofed/compromised points response from
        # redirecting us to an arbitrary host (e.g. a cloud metadata endpoint).
        if not forecast_url.startswith(f"{self._base_url}/"):
            raise ValueError(f"unexpected forecast URL from NWS: {forecast_url!r}")

        self._forecast_url = forecast_url
        return self._forecast_url

    async def get_forecast(self) -> WeatherForecast:
        """Fetch the current multi-period forecast for our location."""
        forecast_url = await self._resolve_forecast_url()
        resp = await self._http.get(forecast_url, headers=self._headers)
        resp.raise_for_status()

        periods: list[WeatherForecastPeriod] = []
        for raw in resp.json()["properties"]["periods"]:
            periods.append(
                WeatherForecastPeriod(
                    name=raw.get("name", ""),
                    # startTime is ISO 8601 with offset, e.g. 2026-06-01T12:00:00-05:00
                    start=datetime.fromisoformat(raw["startTime"]),
                    temperature=float(raw["temperature"]),
                    temperature_unit=raw.get("temperatureUnit", "F"),
                    short_forecast=raw.get("shortForecast", ""),
                )
            )

        return WeatherForecast(periods=periods)
