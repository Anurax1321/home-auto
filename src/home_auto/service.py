"""The orchestrator: one poll cycle wires sources -> engine -> notifications.

`HomeAutoService.poll()` is the heart of the app. It is written defensively:
each external call is isolated so a single failing API (ComEd hiccup, weather
timeout) degrades that one field instead of crashing the whole cycle. The
scheduler in __main__ calls poll() on a fixed interval.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from .config import Config
from .engine.charge_window import recommend_charge_window
from .engine.decision import PriceMonitor, classify
from .engine.triggers import evaluate_triggers
from .notify.manager import NotificationManager
from .settings_store import SettingsStore, ThresholdSettings
from .sources.comed import ComEdClient
from .sources.weather import WeatherClient
from .state import Snapshot
from .triggers import TriggerStore

log = logging.getLogger(__name__)

# Weather changes slowly and NWS asks us to be polite; refresh at most this often.
_WEATHER_MAX_AGE = timedelta(minutes=30)


class HomeAutoService:
    def __init__(
        self,
        config: Config,
        comed: ComEdClient,
        weather: WeatherClient,
        notifier: NotificationManager,
        settings_store: SettingsStore,
        trigger_store: TriggerStore,
    ) -> None:
        self._config = config
        self._comed = comed
        self._weather = weather
        self._notifier = notifier
        self._monitor = PriceMonitor(config.thresholds)

        # Stores the dashboard reads/writes (thresholds + user triggers).
        self.settings_store = settings_store
        self.trigger_store = trigger_store

        # Public snapshot the dashboard reads.
        self.snapshot = Snapshot()

        # Throttle state for the weather fetch.
        self._last_weather_at: datetime | None = None

        # When each trigger last fired, for cooldown enforcement (id -> time).
        self._trigger_last_fired: dict[str, datetime] = {}

    @property
    def recent_alerts(self):
        """Recent alerts retained by the dashboard channel (empty if disabled)."""
        dash = self._notifier.dashboard_channel
        return dash.recent if dash is not None else []

    @classmethod
    def build(
        cls,
        config: Config,
        http: httpx.AsyncClient,
        settings_store: SettingsStore | None = None,
        trigger_store: TriggerStore | None = None,
    ) -> "HomeAutoService":
        """Construct the service and all its collaborators from config.

        Saved threshold overrides (data/settings.json) are layered over the
        config defaults here, so a value the user set from the dashboard last
        session survives a restart.
        """
        settings_store = settings_store or SettingsStore.default()
        trigger_store = trigger_store or TriggerStore.default()

        saved = settings_store.load_thresholds()
        if saved is not None:
            config.thresholds.high_price_cents = saved.high_price_cents
            config.thresholds.low_price_cents = saved.low_price_cents

        comed = ComEdClient(http)
        weather = WeatherClient(
            http,
            latitude=config.location.latitude,
            longitude=config.location.longitude,
        )
        notifier = NotificationManager.from_config(config, http)
        return cls(config, comed, weather, notifier, settings_store, trigger_store)

    def update_thresholds(self, high_price_cents: float, low_price_cents: float) -> ThresholdSettings:
        """Change the cheap/expensive thresholds live and persist them.

        Validates the pair (via ThresholdSettings), updates the running config
        and the price monitor, saves the override, and re-classifies the current
        snapshot so the dashboard reflects the change immediately.
        """
        settings = ThresholdSettings(
            high_price_cents=high_price_cents, low_price_cents=low_price_cents
        )
        self._config.thresholds.high_price_cents = settings.high_price_cents
        self._config.thresholds.low_price_cents = settings.low_price_cents
        # The monitor holds its own reference to the thresholds object; it is the
        # same object we just mutated, so its future classifications use the new
        # values. Re-classify the latest price now for an immediate UI update.
        if self.snapshot.latest_price is not None:
            self.snapshot.price_state = classify(
                self.snapshot.latest_price.price_cents, self._config.thresholds
            )
        self.settings_store.save_thresholds(settings)
        return settings

    async def get_price_history(self, start: datetime, end: datetime):
        """Fetch raw 5-minute prices for a range (used by the history API)."""
        return await self._comed.get_history(start, end)

    async def poll(self) -> None:
        """Run one full cycle: fetch prices/weather, evaluate, notify, snapshot."""
        now = datetime.now(timezone.utc)
        errors: list[str] = []

        # --- Prices (the core data; if this fails we keep the old snapshot) ---
        prices = []
        try:
            prices = await self._comed.get_5min_feed()
        except Exception as exc:  # noqa: BLE001
            log.exception("failed to fetch ComEd 5-minute feed")
            errors.append(f"price feed: {exc}")

        if prices:
            latest = prices[-1]
            self.snapshot.latest_price = latest
            self.snapshot.recent_prices = prices
            self.snapshot.price_state = classify(
                latest.price_cents, self._config.thresholds
            )

            # Alert only on a state transition (handled inside the monitor).
            alert = self._monitor.update(latest)
            if alert is not None:
                await self._notifier.dispatch(alert)

            # Recommend the cheapest upcoming charge window from recent history.
            window, forecast = recommend_charge_window(
                history=prices,
                session_hours=self._config.charging.session_hours,
                deadline_hour=self._config.charging.deadline_hour,
                tz=self._config.location.tz,
                now=now,
            )
            self.snapshot.charge_window = window
            self.snapshot.forecast = forecast

        # --- Current-hour average (nice-to-have; non-fatal) ---
        try:
            self.snapshot.current_hour_average = (
                await self._comed.get_current_hour_average()
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to fetch current-hour average: %s", exc)
            errors.append(f"hour average: {exc}")

        # --- User-defined triggers (notify on matching conditions) ---
        try:
            await self._evaluate_triggers(now)
        except Exception as exc:  # noqa: BLE001 - never let triggers break the poll
            log.exception("trigger evaluation failed")
            errors.append(f"triggers: {exc}")

        # --- Weather (throttled; non-fatal) ---
        if self._weather_is_stale(now):
            try:
                self.snapshot.weather = await self._weather.get_forecast()
                self._last_weather_at = now
            except Exception as exc:  # noqa: BLE001
                log.warning("failed to fetch weather: %s", exc)
                errors.append(f"weather: {exc}")

        self.snapshot.updated_at = now
        self.snapshot.last_error = "; ".join(errors) if errors else None

    async def _evaluate_triggers(self, now: datetime) -> None:
        """Check every stored trigger against the latest readings and notify.

        Triggers are reloaded each cycle so edits from the dashboard take effect
        without a restart. Cooldowns are tracked in-memory per trigger id.
        """
        triggers = self.trigger_store.list()
        if not triggers:
            return

        price = (
            self.snapshot.latest_price.price_cents
            if self.snapshot.latest_price is not None
            else None
        )
        fired = evaluate_triggers(
            triggers,
            price_cents=price,
            hour_average=self.snapshot.current_hour_average,
            now=now,
            last_fired=self._trigger_last_fired,
        )
        for trigger, alert in fired:
            self._trigger_last_fired[trigger.id] = now
            await self._notifier.dispatch(alert, channels=trigger.action.channels)

    def _weather_is_stale(self, now: datetime) -> bool:
        """True if we have never fetched weather or it is older than the max age."""
        if self._last_weather_at is None:
            return True
        return (now - self._last_weather_at) >= _WEATHER_MAX_AGE
