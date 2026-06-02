"""FastAPI app serving the dashboard HTML + a JSON status API.

Two surfaces:
    GET /             -> the dashboard page (HTML, auto-refreshing via JS)
    GET /api/status   -> the full current snapshot as JSON (the page polls this)
    GET /healthz      -> tiny liveness probe for Docker/monitoring

The JSON serialization lives here (not on the models) so the wire format can
evolve independently of the internal dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..models import (
    Alert,
    ChargeWindow,
    PricePoint,
    WeatherForecast,
)
from ..service import HomeAutoService

# Templates live next to this file.
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _iso(value) -> str | None:
    """ISO-8601 string for a datetime, or None."""
    return value.isoformat() if value is not None else None


def _serialize_price(point: PricePoint) -> dict:
    return {"t": point.timestamp.isoformat(), "p": round(point.price_cents, 2)}


def _serialize_window(window: ChargeWindow | None) -> dict | None:
    if window is None:
        return None
    return {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "average_price_cents": round(window.average_price_cents, 2),
        "duration_hours": round(window.duration_hours, 1),
    }


def _serialize_weather(weather: WeatherForecast | None) -> dict | None:
    if weather is None:
        return None
    return {
        "periods": [
            {
                "name": p.name,
                "start": p.start.isoformat(),
                "temperature": p.temperature,
                "unit": p.temperature_unit,
                "short_forecast": p.short_forecast,
            }
            for p in weather.periods[:6]  # next few periods is plenty for the UI
        ]
    }


def _serialize_alert(alert: Alert) -> dict:
    return {
        "level": alert.level.value,
        "title": alert.title,
        "message": alert.message,
        "created_at": alert.created_at.isoformat(),
    }


def build_status(service: HomeAutoService) -> dict:
    """Turn the service's current snapshot into a JSON-serializable dict."""
    snap = service.snapshot
    cfg = service._config  # internal read is fine within the same package
    return {
        "updated_at": _iso(snap.updated_at),
        "latest_price": _serialize_price(snap.latest_price)
        if snap.latest_price
        else None,
        "price_state": snap.price_state.value if snap.price_state else None,
        "current_hour_average": (
            round(snap.current_hour_average, 2)
            if snap.current_hour_average is not None
            else None
        ),
        "thresholds": {
            "high": cfg.thresholds.high_price_cents,
            "low": cfg.thresholds.low_price_cents,
        },
        "charge_window": _serialize_window(snap.charge_window),
        "weather": _serialize_weather(snap.weather),
        "recent_prices": [_serialize_price(p) for p in snap.recent_prices],
        "forecast": [_serialize_price(p) for p in snap.forecast],
        "alerts": [_serialize_alert(a) for a in service.recent_alerts],
        "last_error": snap.last_error,
    }


def create_app(service: HomeAutoService) -> FastAPI:
    """Create the FastAPI app bound to a running service instance."""
    app = FastAPI(title="home-auto", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        # The heavy data is loaded by JS from /api/status; the template just
        # needs the request object for url building.
        return _TEMPLATES.TemplateResponse(request, "dashboard.html", {})

    @app.get("/api/status")
    async def status():
        return build_status(service)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app
