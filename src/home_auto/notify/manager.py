"""NotificationManager: fans each alert out to every enabled channel.

Built from config via `from_config`, which inspects the notifications section
and instantiates only the channels the user turned on. The dashboard channel is
kept as a named attribute so the web app can read recent alerts from it.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..config import Config
from ..models import Alert
from .base import NotificationChannel
from .dashboard_channel import DashboardChannel
from .email_channel import EmailChannel
from .ntfy_channel import NtfyChannel

log = logging.getLogger(__name__)


class NotificationManager:
    def __init__(
        self,
        channels: list[NotificationChannel],
        dashboard_channel: DashboardChannel | None = None,
    ) -> None:
        self._channels = channels
        # Direct handle for the web UI (may be None if the user disabled it).
        self.dashboard_channel = dashboard_channel

    @property
    def channels(self) -> list[NotificationChannel]:
        return self._channels

    async def dispatch(
        self, alert: Alert, channels: list[str] | None = None
    ) -> None:
        """Send one alert through the enabled channels concurrently.

        If `channels` is given (a list of channel names), the alert goes only to
        those channels; an empty list or None means all enabled channels. This
        lets a trigger target, say, only ntfy. Unknown names are simply ignored.

        return_exceptions=True ensures one channel failing never prevents the
        others from delivering, and never propagates out to the polling loop.
        """
        targets = self._channels
        if channels:
            wanted = set(channels)
            targets = [c for c in self._channels if c.name in wanted]
        if not targets:
            return
        results = await asyncio.gather(
            *(channel.send(alert) for channel in targets),
            return_exceptions=True,
        )
        for channel, result in zip(targets, results):
            if isinstance(result, Exception):
                log.error("channel %s failed: %r", channel.name, result)

    @classmethod
    def from_config(cls, config: Config, http: httpx.AsyncClient) -> "NotificationManager":
        """Construct the manager with exactly the channels enabled in config."""
        channels: list[NotificationChannel] = []
        dashboard: DashboardChannel | None = None

        notif = config.notifications

        if notif.dashboard.enabled:
            dashboard = DashboardChannel()
            channels.append(dashboard)

        if notif.ntfy.enabled and notif.ntfy.topic:
            channels.append(
                NtfyChannel(http, server=notif.ntfy.server, topic=notif.ntfy.topic)
            )

        if notif.email.enabled and notif.email.to_addrs:
            channels.append(EmailChannel(notif.email))

        log.info(
            "notifications enabled: %s",
            ", ".join(c.name for c in channels) or "(none)",
        )
        return cls(channels, dashboard_channel=dashboard)
