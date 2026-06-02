"""ntfy push channel: free phone push notifications via https://ntfy.sh.

You install the ntfy app, subscribe to a topic (any long, hard-to-guess
string), and the app receives a push whenever we POST to that topic. The topic
name is effectively the password, so pick something unguessable.
"""

from __future__ import annotations

import logging

import httpx

from ..models import Alert, AlertLevel
from .base import NotificationChannel

log = logging.getLogger(__name__)


class NtfyChannel(NotificationChannel):
    name = "ntfy"

    def __init__(self, http: httpx.AsyncClient, server: str, topic: str) -> None:
        self._http = http
        self._server = server.rstrip("/")
        self._topic = topic

    async def send(self, alert: Alert) -> None:
        url = f"{self._server}/{self._topic}"
        # ntfy reads metadata from headers; values must be ASCII-safe.
        headers = {
            "Title": alert.title,
            "Priority": "high" if alert.level == AlertLevel.WARNING else "default",
            "Tags": "zap" if alert.level == AlertLevel.WARNING else "bulb",
        }
        try:
            resp = await self._http.post(
                url, content=alert.message.encode("utf-8"), headers=headers
            )
            resp.raise_for_status()
        except Exception:  # noqa: BLE001 - never let a channel break the loop
            log.exception("ntfy notification failed")
