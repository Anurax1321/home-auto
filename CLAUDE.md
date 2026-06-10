# home-auto — project guide for Claude

Monitor ComEd (Illinois) electricity prices + weather and optimize home loads (Tesla, thermostat, appliances). See README.md for the full picture.

## Stack

- Python 3.12, `src/` layout (package: `home_auto`, importable via `PYTHONPATH=src`).
- httpx (async HTTP), FastAPI + uvicorn (dashboard), APScheduler (poll loop), pydantic (config/models), PyYAML + python-dotenv (config/secrets).
- Tests: pytest + pytest-asyncio (auto mode) + respx (mocks httpx; tests never hit the network).

## Commands

```bash
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest                                  # unit tests
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py        # live end-to-end
PYTHONPATH=src .venv/bin/python -m home_auto                 # run service + dashboard
```

- Dashboard: **http://localhost:8080** (`/`, `/api/status`, `/api/history`, `/api/settings`, `/api/triggers`, `/healthz`).
- Config: `config.yaml` (copy from `config.example.yaml`). Secrets: `.env`. Runtime state (live thresholds, triggers): `data/*.json` (override dir with `HOME_AUTO_DATA_DIR`). All git-ignored.

## Conventions

- Prices are in **cents/kWh**. Timestamps are timezone-aware; ComEd data is UTC, user-facing times use `location.timezone` (default `America/Chicago`).
- Secrets come only from env vars, never from YAML, and must never be logged or returned by the API.
- Notification channels implement `notify/base.py:NotificationChannel` and must never raise out of `send()`.
- Each external call in `service.poll()` is isolated so one failing API degrades a field, not the whole cycle.
- Adapters for new data sources / actions / channels go behind their existing interfaces; keep optimization logic in testable Python, not framework glue.
- Runtime-editable state (thresholds, triggers) lives in `data/*.json` via `storage.py` (atomic writes); never write it back into `config.yaml`. Client input never sets a file path; trigger ids are server-generated.
- Triggers are notify-only today but `action.type` is a stub for future device control (Phase 2+). Engine logic stays pure in `engine/triggers.py`; the service owns cooldown state and dispatch.
- Dashboard JS renders all API/user strings with `textContent`, never `innerHTML` (XSS-safe). Light theme is default; dark is a toggle.
- Always run `pytest` after changes. The data clients are data-handling code: run a security check after touching them, the web app, or the notifier.

## Key external APIs

- ComEd Hourly Pricing: `https://hourlypricing.comed.com/api?type=5minutefeed` (and `currenthouraverage`). Free, no auth.
- NWS weather: `https://api.weather.gov/points/{lat},{lon}` -> forecast URL (must stay under `api.weather.gov`). Needs a User-Agent header.

## Roadmap

Phase 1 (monitor/alert/recommend) is done. Next: Phase 2 Tesla Fleet API control, Phase 3 thermostat (lean Ecobee), Phase 4 smart plugs, Phase 5 Alexa/Home Assistant.
