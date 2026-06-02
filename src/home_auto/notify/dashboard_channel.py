"""Dashboard channel: keeps the most recent alerts in memory for the web UI.

Unlike email/push, this channel doesn't send anything outward; it just retains
a bounded history that the FastAPI dashboard reads and renders. Always cheap and
failure-free, so it's enabled by default.
"""

from __future__ import annotations

from collections import deque

from ..models import Alert
from .base import NotificationChannel


class DashboardChannel(NotificationChannel):
    name = "dashboard"

    def __init__(self, max_alerts: int = 50) -> None:
        # deque with maxlen auto-drops the oldest alert when full.
        self._alerts: deque[Alert] = deque(maxlen=max_alerts)

    async def send(self, alert: Alert) -> None:
        self._alerts.appendleft(alert)  # newest first

    @property
    def recent(self) -> list[Alert]:
        """Recent alerts, newest first."""
        return list(self._alerts)
