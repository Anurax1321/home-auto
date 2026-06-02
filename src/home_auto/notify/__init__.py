"""Pluggable notification channels (email, ntfy push, dashboard).

The user enables any combination in config; the NotificationManager fans each
alert out to every enabled channel. Adding a channel later (Alexa, SMS) means
writing one class that implements NotificationChannel.
"""

from .base import NotificationChannel
from .dashboard_channel import DashboardChannel
from .email_channel import EmailChannel
from .manager import NotificationManager
from .ntfy_channel import NtfyChannel

__all__ = [
    "NotificationChannel",
    "DashboardChannel",
    "EmailChannel",
    "NtfyChannel",
    "NotificationManager",
]
