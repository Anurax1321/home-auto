"""FastAPI app serving the dashboard HTML + a JSON status API.

Two surfaces:
    GET /             -> the dashboard page (HTML, auto-refreshing via JS)
    GET /api/status   -> the full current snapshot as JSON (the page polls this)
    GET /healthz      -> tiny liveness probe for Docker/monitoring

The JSON serialization lives here (not on the models) so the wire format can
evolve independently of the internal dataclasses.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..engine.aggregate import daily_averages, hourly_averages
from ..models import (
    Alert,
    ChargeWindow,
    PricePoint,
    WeatherForecast,
)
from ..service import HomeAutoService
from ..settings_store import ThresholdSettings
from ..triggers import TriggerCreate

# How far back each chart range looks, and how to downsample it for the chart:
#   "raw"    -> the snapshot's 5-minute points (1D, served without a fetch)
#   "hourly" -> one averaged point per hour (1W, 1M)
#   "daily"  -> one averaged point per day  (1Y; a year of hourly is too dense)
_RANGES = {
    "1d": (timedelta(days=1), "raw"),
    "1w": (timedelta(days=7), "hourly"),
    "1m": (timedelta(days=30), "hourly"),
    "1y": (timedelta(days=365), "daily"),
}

# How to collapse fetched points for each downsampling mode.
_AGGREGATORS = {"hourly": hourly_averages, "daily": daily_averages}

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


# Seconds to cache the 1W/1M history so repeated dashboard refreshes don't proxy
# an unthrottled external fetch on every request (the underlying data is only
# 5-minute granularity, so a few minutes of staleness is invisible).
_HISTORY_TTL = 300.0


def create_app(service: HomeAutoService) -> FastAPI:
    """Create the FastAPI app bound to a running service instance."""
    app = FastAPI(title="home-auto", version="0.1.0")

    # range -> (monotonic_time_fetched, payload). Only used for 1w/1m.
    history_cache: dict[str, tuple[float, dict]] = {}

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

    # ----- Price history for the 1D / 1W / 1M chart ranges -----
    @app.get("/api/history")
    async def history(range: str = "1d"):
        if range not in _RANGES:
            raise HTTPException(
                status_code=400, detail="range must be 1d, 1w, 1m, or 1y"
            )
        span, mode = _RANGES[range]

        if mode == "raw":
            # The current snapshot already holds the last ~24h of 5-minute prices.
            points = service.snapshot.recent_prices
            return {"range": range, "points": [_serialize_price(p) for p in points]}

        # Longer ranges hit the external API; serve a recent cached copy if we
        # have one (1Y in particular is a multi-MB fetch we don't want to repeat).
        cached = history_cache.get(range)
        if cached is not None and (time.monotonic() - cached[0]) < _HISTORY_TTL:
            return cached[1]

        now = datetime.now(timezone.utc)
        try:
            points = await service.get_price_history(now - span, now)
        except Exception as exc:  # noqa: BLE001 - report cleanly, don't 500
            raise HTTPException(
                status_code=502, detail=f"could not load history: {exc}"
            ) from exc
        points = _AGGREGATORS[mode](points)

        payload = {"range": range, "points": [_serialize_price(p) for p in points]}
        history_cache[range] = (time.monotonic(), payload)
        return payload

    # ----- Editable price thresholds -----
    @app.get("/api/settings")
    async def get_settings():
        cfg = service._config
        return {
            "thresholds": {
                "high_price_cents": cfg.thresholds.high_price_cents,
                "low_price_cents": cfg.thresholds.low_price_cents,
            }
        }

    @app.post("/api/settings")
    async def post_settings(thresholds: ThresholdSettings):
        # Pydantic has already validated (positive, low <= high) before we get here.
        saved = service.update_thresholds(
            high_price_cents=thresholds.high_price_cents,
            low_price_cents=thresholds.low_price_cents,
        )
        return {"thresholds": saved.model_dump()}

    # ----- Triggers CRUD -----
    @app.get("/api/triggers")
    async def list_triggers():
        return [t.model_dump() for t in service.trigger_store.list()]

    @app.post("/api/triggers")
    async def create_trigger(trigger: TriggerCreate):
        try:
            created = service.trigger_store.add(trigger)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return created.model_dump()

    @app.patch("/api/triggers/{trigger_id}")
    async def update_trigger(trigger_id: str, trigger: TriggerCreate):
        updated = service.trigger_store.update(trigger_id, trigger)
        if updated is None:
            raise HTTPException(status_code=404, detail="trigger not found")
        return updated.model_dump()

    @app.delete("/api/triggers/{trigger_id}")
    async def delete_trigger(trigger_id: str):
        if not service.trigger_store.delete(trigger_id):
            raise HTTPException(status_code=404, detail="trigger not found")
        return {"deleted": trigger_id}

    return app
