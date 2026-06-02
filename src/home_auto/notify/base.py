"""The notification channel interface every channel implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Alert


class NotificationChannel(ABC):
    """One delivery mechanism for alerts (email, push, dashboard, ...).

    Channels are async because most do network I/O. A channel should never
    raise out of `send`: a failure in one channel must not stop the others or
    crash the polling loop. The manager logs failures; channels return normally.
    """

    #: Human-readable name used in logs and the dashboard.
    name: str = "channel"

    @abstractmethod
    async def send(self, alert: Alert) -> None:
        """Deliver a single alert. Must not raise; handle errors internally."""
        raise NotImplementedError
