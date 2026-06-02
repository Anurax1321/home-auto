"""Configuration loading + validation.

The service reads a YAML file (default: ./config.yaml) for everything that is
safe to keep in version-controlled-ish settings, and pulls *secrets* (SMTP
password, etc.) from environment variables / a .env file. Keeping secrets out
of the YAML is deliberate: config.yaml is easy to accidentally share.

All settings are validated by pydantic, so a typo or wrong type fails loudly at
startup instead of causing a confusing crash hours later.
"""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LocationConfig(BaseModel):
    """Where the home is (drives the weather lookup) and its timezone."""

    # Range-validated so an obvious typo fails loudly at startup.
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    timezone: str = "America/Chicago"

    @property
    def tz(self) -> ZoneInfo:
        """The configured timezone as a usable tzinfo object."""
        return ZoneInfo(self.timezone)


class PollingConfig(BaseModel):
    interval_seconds: int = 300


class ThresholdConfig(BaseModel):
    high_price_cents: float = 10.0
    low_price_cents: float = 3.0


class ChargingConfig(BaseModel):
    session_hours: float = 4.0
    deadline_hour: int = 7


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    from_addr: str = ""
    to_addrs: list[str] = Field(default_factory=list)
    # Never read from YAML; populated from HOME_AUTO_EMAIL_PASSWORD at load time.
    password: str = ""


class NtfyConfig(BaseModel):
    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str = ""


class DashboardChannelConfig(BaseModel):
    enabled: bool = True


class NotificationsConfig(BaseModel):
    email: EmailConfig = Field(default_factory=EmailConfig)
    ntfy: NtfyConfig = Field(default_factory=NtfyConfig)
    dashboard: DashboardChannelConfig = Field(default_factory=DashboardChannelConfig)


class DashboardConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class Config(BaseModel):
    """Top-level configuration object for the whole service."""

    location: LocationConfig
    polling: PollingConfig = Field(default_factory=PollingConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    charging: ChargingConfig = Field(default_factory=ChargingConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)


def load_config(path: str | None = None) -> Config:
    """Load and validate configuration.

    Resolution order for the YAML path:
        1. The `path` argument, if given.
        2. The HOME_AUTO_CONFIG environment variable.
        3. ./config.yaml

    Secrets are layered on top from the environment after the YAML is parsed.
    """
    load_dotenv()  # harmless if there is no .env file

    resolved = path or os.environ.get("HOME_AUTO_CONFIG", "config.yaml")
    with open(resolved, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    config = Config(**raw)

    # Layer secrets from the environment on top of the parsed config.
    email_password = os.environ.get("HOME_AUTO_EMAIL_PASSWORD")
    if email_password:
        config.notifications.email.password = email_password

    return config
