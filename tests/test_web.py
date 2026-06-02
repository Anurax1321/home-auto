"""Tests for the dashboard JSON API and page, via FastAPI's TestClient."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from home_auto.config import Config, LocationConfig
from home_auto.models import PricePoint, PriceState
from home_auto.service import HomeAutoService
from home_auto.web.app import create_app


def _service() -> HomeAutoService:
    config = Config(location=LocationConfig(latitude=41.0, longitude=-87.0))
    # build() only constructs clients (no network), so a real AsyncClient is fine.
    return HomeAutoService.build(config, httpx.AsyncClient())


def test_status_endpoint_serializes_snapshot():
    service = _service()
    service.snapshot.latest_price = PricePoint(
        datetime.now(timezone.utc), price_cents=2.8
    )
    service.snapshot.price_state = PriceState.CHEAP

    client = TestClient(create_app(service))
    resp = client.get("/api/status")
    assert resp.status_code == 200

    body = resp.json()
    assert body["latest_price"]["p"] == 2.8
    assert body["price_state"] == "cheap"
    assert body["thresholds"]["low"] == 3.0


def test_healthz_and_dashboard_page():
    client = TestClient(create_app(_service()))
    assert client.get("/healthz").json() == {"status": "ok"}

    page = client.get("/")
    assert page.status_code == 200
    assert "home-auto" in page.text
