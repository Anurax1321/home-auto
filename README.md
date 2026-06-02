# home-auto

Monitor real-time **ComEd** electricity prices (Illinois) plus the local **weather**, and optimize your home's big loads around them: when to charge the Tesla, when to run appliances, and (later) how to drive the thermostat. It raises alerts when prices cross thresholds you set and recommends the cheapest upcoming window to charge.

> **Status: Phase 1 complete.** The service reads prices + weather, classifies them, alerts you, recommends a charge window, and shows everything on a local dashboard. Device *control* (Tesla, thermostat, plugs) lands in later phases. See the [Roadmap](#roadmap).

---

## Why this works

ComEd publishes a free, no-auth JSON feed of the live wholesale energy-supply price. In a typical day that price swings roughly **0.6 to 13 cents/kWh**, about a 20x spread. The whole point of this project is to push movable loads (car, water heater, etc.) toward the cheap valleys and away from the expensive peaks.

Weather comes from the US National Weather Service (`api.weather.gov`), which is also free and needs no key.

---

## Architecture

```
                 ┌─────────────────────────────────────────┐
                 │   home-auto service  (Python)             │
   READ          │                                           │
 ComEd API ─────▶│  Sources ─▶ Decision Engine ─▶ (Actions)  │  (Actions arrive in
 Weather (NWS) ─▶│            thresholds +        coming      │   later phases:
                 │            best-window calc    phases      │   Tesla / thermostat /
                 │                  │                         │   smart plugs)
                 │                  ▼                         │
                 │            Notifier (pluggable)            │─▶ Email / ntfy push / dashboard
                 │            + local web dashboard           │
                 └─────────────────────────────────────────┘
```

**Data flow:** every `interval_seconds`, the scheduler runs one `poll()` that fetches prices + weather, classifies the current price, fires an alert on any state change, recomputes the best charge window, and writes a fresh snapshot that the dashboard reads.

### Module map (`src/home_auto/`)

| Module | Responsibility |
| --- | --- |
| `config.py` | Load + validate `config.yaml`; inject secrets from env vars. |
| `models.py` | Shared dataclasses (`PricePoint`, `ChargeWindow`, `Alert`, ...). |
| `sources/comed.py` | ComEd Hourly Pricing API client. |
| `sources/weather.py` | NWS forecast client (two-step points -> forecast lookup). |
| `engine/decision.py` | Classify price vs. thresholds; alert only on state changes. |
| `engine/charge_window.py` | Build an hourly price profile and find the cheapest window. |
| `notify/` | Pluggable channels (`email`, `ntfy`, `dashboard`) + fan-out manager. |
| `state.py` | In-memory snapshot the dashboard renders. |
| `service.py` | Orchestrator: one `poll()` wires sources -> engine -> notify. |
| `web/app.py` | FastAPI app: dashboard page + JSON status API. |
| `__main__.py` | Entry point: runs the scheduler + web server together. |

---

## Quick start

Requires **Python 3.12+**.

```bash
# 1. Create a virtual environment and install dependencies.
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

# 2. Create your config from the example (config.yaml is git-ignored).
cp config.example.yaml config.yaml
#    Edit config.yaml: set your latitude/longitude, thresholds, and which
#    notification channels to enable.

# 3. (Optional) Create your secrets file for the email channel.
cp .env.example .env       # then fill in HOME_AUTO_EMAIL_PASSWORD if using email

# 4. Run it.
PYTHONPATH=src .venv/bin/python -m home_auto
```

Then open the dashboard at **http://localhost:8080**.

### Run with Docker

Once Docker is available (in WSL, enable "WSL integration" in Docker Desktop):

```bash
cp config.example.yaml config.yaml   # edit it
cp .env.example .env                  # edit it
docker compose up -d
```

---

## Configuration

All non-secret settings live in `config.yaml` (copy from `config.example.yaml`). Secrets live in `.env`. Both are git-ignored. Highlights:

- **`location`** — your latitude/longitude (for weather) and timezone.
- **`thresholds`** — `high_price_cents` (alert + "hold off") and `low_price_cents` ("cheap, good to run loads"), in cents/kWh.
- **`charging`** — `session_hours` (how long a charge takes) and `deadline_hour` (must finish by this local hour).
- **`notifications`** — enable any combination of `email`, `ntfy`, and `dashboard`.
- **`dashboard`** — `host`/`port` for the web UI.

### Notification channels

You choose which to turn on; each fires when the price state changes (cheap / normal / expensive).

- **dashboard** — on by default; keeps recent alerts visible in the web UI. No setup.
- **ntfy** — free phone push. Install the [ntfy](https://ntfy.sh) app, pick a long hard-to-guess topic, set it in `config.yaml`, and subscribe to it in the app. The topic name is effectively a password.
- **email** — set the SMTP fields in `config.yaml` and put the password in `HOME_AUTO_EMAIL_PASSWORD` in `.env` (for Gmail, use an "app password").

---

## Best-time-to-charge

ComEd's public feed gives past + present prices, not a guaranteed forecast. So the calculator builds a "typical day" profile by averaging recent prices per hour-of-day, projects that forward, and picks the cheapest contiguous block of `session_hours` that finishes before `deadline_hour`. It sharpens as more history accumulates. If ComEd later exposes a day-ahead feed, only the projection step needs to change. The window appears on the dashboard.

---

## HTTP API

| Endpoint | Description |
| --- | --- |
| `GET /` | The dashboard page (auto-refreshes every 30s). |
| `GET /api/status` | Full current snapshot as JSON (price, state, charge window, weather, recent prices, alerts). |
| `GET /healthz` | Liveness probe. |

---

## Testing

```bash
.venv/bin/python -m pytest                       # unit tests (network mocked)
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py   # live end-to-end against real APIs
```

Unit tests mock all network calls with `respx`, so they are fast and offline. The smoke test hits the real ComEd + NWS APIs and prints one live snapshot.

---

## Security notes

- Secrets (SMTP password) are read only from the environment, never from `config.yaml`, and are never logged or returned by the API.
- The weather client only fetches forecast URLs under `api.weather.gov` (guards against a spoofed redirect).
- The dashboard has **no authentication** and binds to `0.0.0.0` by default so other devices on your LAN can reach it. The data is low-sensitivity (prices, weather, your coordinates). If your host is exposed beyond your home network, put it behind a reverse proxy with auth or set `dashboard.host` to `127.0.0.1`.

---

## Roadmap

- **Phase 1 — Monitor + Alert + Recommend** ✅ *(this release; no control hardware needed)*
- **Phase 2 — Tesla charging control** via the Tesla Fleet API (auto-schedule into the cheapest window).
- **Phase 3 — Thermostat + weather logic** (pre-cool/pre-heat around price spikes; thermostat TBD, Ecobee preferred).
- **Phase 4 — Appliance control** via Shelly/Kasa smart plugs.
- **Phase 5 — Voice + polish** (Alexa announcements/queries, optional Home Assistant integration).
