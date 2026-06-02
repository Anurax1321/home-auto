"""Tests for the NWS weather client. Both API steps are mocked with respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from home_auto.sources.weather import WeatherClient


@respx.mock
async def test_get_forecast_two_step_lookup():
    # Step 1: /points/{lat},{lon} returns the forecast URL.
    respx.get(url__startswith="https://api.weather.gov/points/").mock(
        return_value=httpx.Response(
            200,
            json={"properties": {"forecast": "https://api.weather.gov/fc/test"}},
        )
    )
    # Step 2: the forecast URL returns periods.
    respx.get("https://api.weather.gov/fc/test").mock(
        return_value=httpx.Response(
            200,
            json={
                "properties": {
                    "periods": [
                        {
                            "name": "This Afternoon",
                            "startTime": "2026-06-01T12:00:00-05:00",
                            "temperature": 75,
                            "temperatureUnit": "F",
                            "shortForecast": "Sunny",
                        }
                    ]
                }
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = WeatherClient(http, latitude=41.8781, longitude=-87.6298)
        forecast = await client.get_forecast()

    assert forecast.current is not None
    assert forecast.current.temperature == 75
    assert forecast.current.short_forecast == "Sunny"


@respx.mock
async def test_forecast_url_is_cached():
    points_route = respx.get(url__startswith="https://api.weather.gov/points/").mock(
        return_value=httpx.Response(
            200, json={"properties": {"forecast": "https://api.weather.gov/fc/test"}}
        )
    )
    respx.get("https://api.weather.gov/fc/test").mock(
        return_value=httpx.Response(200, json={"properties": {"periods": []}})
    )
    async with httpx.AsyncClient() as http:
        client = WeatherClient(http, 41.0, -87.0)
        await client.get_forecast()
        await client.get_forecast()

    # The points endpoint should only be hit once (URL cached after first call).
    assert points_route.call_count == 1


@respx.mock
async def test_rejects_forecast_url_outside_nws():
    # A spoofed response pointing the forecast URL at another host must be refused.
    respx.get(url__startswith="https://api.weather.gov/points/").mock(
        return_value=httpx.Response(
            200,
            json={"properties": {"forecast": "http://169.254.169.254/latest/meta-data"}},
        )
    )
    async with httpx.AsyncClient() as http:
        client = WeatherClient(http, 41.0, -87.0)
        with pytest.raises(ValueError):
            await client.get_forecast()
