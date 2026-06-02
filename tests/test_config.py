"""Tests for config loading, defaults, and secret injection from the env."""

from __future__ import annotations

import textwrap

from home_auto.config import load_config


def test_load_config_applies_defaults_and_env_secret(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            location:
              latitude: 41.0
              longitude: -87.0
            thresholds:
              high_price_cents: 9
            notifications:
              email:
                enabled: true
                to_addrs: ["me@example.com"]
            """
        )
    )
    monkeypatch.setenv("HOME_AUTO_EMAIL_PASSWORD", "s3cret")

    config = load_config(str(config_file))

    assert config.location.latitude == 41.0
    assert config.thresholds.high_price_cents == 9.0
    assert config.thresholds.low_price_cents == 3.0      # default kept
    assert config.notifications.email.password == "s3cret"  # injected from env
    assert config.location.tz.key == "America/Chicago"   # default timezone usable
