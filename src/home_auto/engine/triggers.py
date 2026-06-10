"""Evaluate user-defined triggers against the latest readings.

Pure logic, no I/O: given the current price/hour-average and the set of triggers,
decide which ones fire *now* (condition met and off cooldown) and build the Alert
for each. The caller (the service) owns the cooldown bookkeeping and the actual
dispatch, which keeps this function trivial to unit-test.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

from ..models import Alert, AlertLevel
from ..triggers import Operator, Trigger

# Map each operator string to the actual comparison.
_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}

# Friendly label for each metric, used in the default alert message.
_METRIC_LABEL = {
    "price": "Price",
    "hour_average": "Hour-average price",
}


class FiredTrigger(NamedTuple):
    """A trigger that fired this cycle, paired with its alert to dispatch."""

    trigger: Trigger
    alert: Alert


def _compare(actual: float, operator: Operator, value: float) -> bool:
    return _OPS[operator](actual, value)


def _build_alert(trigger: Trigger, actual: float, now: datetime) -> Alert:
    """Build the notification for a fired trigger (custom message or default)."""
    if trigger.action.message:
        message = trigger.action.message
    else:
        label = _METRIC_LABEL.get(trigger.metric, trigger.metric)
        message = (
            f"{label} is {actual:.1f} cents/kWh "
            f"({trigger.operator} {trigger.value:.1f})."
        )
    return Alert(
        level=AlertLevel.INFO,
        title=f"Trigger: {trigger.name}",
        message=message,
        created_at=now,
    )


def evaluate_triggers(
    triggers: list[Trigger],
    *,
    price_cents: float | None,
    hour_average: float | None,
    now: datetime,
    last_fired: dict[str, datetime],
) -> list[FiredTrigger]:
    """Return the triggers that should fire right now.

    A trigger fires when it is enabled, its metric value is available, the
    comparison holds, and it is past its cooldown since it last fired. The
    `last_fired` map is read here and updated by the caller for the ones that fire.
    """
    metric_values = {"price": price_cents, "hour_average": hour_average}
    fired: list[FiredTrigger] = []

    for trigger in triggers:
        if not trigger.enabled:
            continue

        actual = metric_values.get(trigger.metric)
        if actual is None:  # metric not available this cycle (e.g. no hour avg)
            continue

        if not _compare(actual, trigger.operator, trigger.value):
            continue

        # Respect the per-trigger cooldown so it doesn't fire every poll.
        previous = last_fired.get(trigger.id)
        if previous is not None:
            if now - previous < timedelta(minutes=trigger.cooldown_minutes):
                continue

        fired.append(FiredTrigger(trigger, _build_alert(trigger, actual, now)))

    return fired
