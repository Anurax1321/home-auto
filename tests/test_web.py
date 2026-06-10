"""Tests for the dashboard JSON API and page, via FastAPI's TestClient."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from home_auto.config import Config, LocationConfig
from home_auto.models import PricePoint, PriceState
from home_auto.service import HomeAutoService
from home_auto.settings_store import SettingsStore
from home_auto.triggers import TriggerStore
from home_auto.web.app import create_app


def _service(tmp_path) -> HomeAutoService:
    config = Config(location=LocationConfig(latitude=41.0, longitude=-87.0))
    # build() only constructs clients (no network); stores point at a temp dir so
    # tests never read or write the real ./data directory.
    return HomeAutoService.build(
        config,
        httpx.AsyncClient(),
        settings_store=SettingsStore(tmp_path / "settings.json"),
        trigger_store=TriggerStore(tmp_path / "triggers.json"),
    )


def test_status_endpoint_serializes_snapshot(tmp_path):
    service = _service(tmp_path)
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


def test_healthz_and_dashboard_page(tmp_path):
    client = TestClient(create_app(_service(tmp_path)))
    assert client.get("/healthz").json() == {"status": "ok"}

    page = client.get("/")
    assert page.status_code == 200
    assert "Home Automation" in page.text


def test_history_1d_uses_snapshot_and_rejects_bad_range(tmp_path):
    service = _service(tmp_path)
    service.snapshot.recent_prices = [
        PricePoint(datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc), 2.0),
        PricePoint(datetime(2026, 6, 1, 0, 5, tzinfo=timezone.utc), 2.5),
    ]
    client = TestClient(create_app(service))

    resp = client.get("/api/history?range=1d")
    assert resp.status_code == 200
    body = resp.json()
    assert body["range"] == "1d"
    assert [pt["p"] for pt in body["points"]] == [2.0, 2.5]

    assert client.get("/api/history?range=bogus").status_code == 400


def test_settings_post_updates_live_and_validates(tmp_path):
    service = _service(tmp_path)
    client = TestClient(create_app(service))

    ok = client.post(
        "/api/settings", json={"high_price_cents": 12.0, "low_price_cents": 2.0}
    )
    assert ok.status_code == 200
    assert service._config.thresholds.high_price_cents == 12.0
    # Persisted to the store so it survives a restart.
    assert service.settings_store.load_thresholds().high_price_cents == 12.0

    # low > high is rejected by validation (422).
    bad = client.post(
        "/api/settings", json={"high_price_cents": 2.0, "low_price_cents": 9.0}
    )
    assert bad.status_code == 422


def test_triggers_crud(tmp_path):
    client = TestClient(create_app(_service(tmp_path)))

    assert client.get("/api/triggers").json() == []

    created = client.post(
        "/api/triggers",
        json={"name": "cheap", "operator": "<", "value": 3.0},
    )
    assert created.status_code == 200
    tid = created.json()["id"]

    listed = client.get("/api/triggers").json()
    assert len(listed) == 1 and listed[0]["name"] == "cheap"

    patched = client.patch(
        f"/api/triggers/{tid}",
        json={"name": "cheaper", "operator": "<", "value": 2.0},
    )
    assert patched.status_code == 200 and patched.json()["name"] == "cheaper"

    assert client.delete(f"/api/triggers/{tid}").status_code == 200
    assert client.delete(f"/api/triggers/{tid}").status_code == 404
    assert client.get("/api/triggers").json() == []
