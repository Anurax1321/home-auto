"""Email channel: send alerts over SMTP.

Uses Python's standard smtplib. SMTP is blocking, so we run the send in a worker
thread (asyncio.to_thread) to avoid stalling the event loop. The password comes
from config (which loaded it from the HOME_AUTO_EMAIL_PASSWORD env var), never
from the YAML file.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from ..config import EmailConfig
from ..models import Alert
from .base import NotificationChannel

log = logging.getLogger(__name__)


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(self, config: EmailConfig) -> None:
        self._cfg = config

    async def send(self, alert: Alert) -> None:
        try:
            # Offload the blocking SMTP conversation to a thread.
            await asyncio.to_thread(self._send_sync, alert)
        except Exception:  # noqa: BLE001 - never let a channel break the loop
            log.exception("email notification failed")

    def _send_sync(self, alert: Alert) -> None:
        """Build and send the message synchronously (runs in a worker thread)."""
        msg = EmailMessage()
        msg["Subject"] = f"[home-auto] {alert.title}"
        msg["From"] = self._cfg.from_addr
        msg["To"] = ", ".join(self._cfg.to_addrs)
        msg.set_content(alert.message)

        with smtplib.SMTP(self._cfg.smtp_host, self._cfg.smtp_port, timeout=15) as smtp:
            smtp.starttls()  # upgrade to an encrypted connection
            if self._cfg.username and self._cfg.password:
                smtp.login(self._cfg.username, self._cfg.password)
            smtp.send_message(msg)
