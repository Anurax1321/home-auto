"""Tests for the notification channels and the fan-out manager."""

from __future__ import annotations

from datetime import datetime, timezone

from home_auto.models import Alert, AlertLevel
from home_auto.notify.base import NotificationChannel
from home_auto.notify.dashboard_channel import DashboardChannel
from home_auto.notify.manager import NotificationManager


def _alert() -> Alert:
    return Alert(
        level=AlertLevel.INFO,
        title="hello",
        message="world",
        created_at=datetime.now(timezone.utc),
    )


async def test_dashboard_channel_retains_alerts_newest_first():
    channel = DashboardChannel(max_alerts=2)
    a1 = _alert()
    a2 = Alert(AlertLevel.WARNING, "second", "msg", datetime.now(timezone.utc))
    await channel.send(a1)
    await channel.send(a2)
    assert channel.recent[0] is a2  # newest first
    assert len(channel.recent) == 2


async def test_dashboard_channel_respects_max():
    channel = DashboardChannel(max_alerts=1)
    await channel.send(_alert())
    await channel.send(_alert())
    assert len(channel.recent) == 1  # oldest dropped


class _FailingChannel(NotificationChannel):
    name = "boom"

    async def send(self, alert: Alert) -> None:
        raise RuntimeError("simulated channel failure")


async def test_manager_isolates_channel_failures():
    dashboard = DashboardChannel()
    manager = NotificationManager(
        channels=[_FailingChannel(), dashboard], dashboard_channel=dashboard
    )
    # One channel raising must not prevent the other from delivering, and the
    # dispatch call itself must not raise.
    await manager.dispatch(_alert())
    assert len(dashboard.recent) == 1


async def test_manager_dispatch_with_no_channels_is_noop():
    manager = NotificationManager(channels=[])
    await manager.dispatch(_alert())  # should simply do nothing
