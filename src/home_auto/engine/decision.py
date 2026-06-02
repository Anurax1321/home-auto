"""Price classification and alerting.

Two pieces:
    classify()      -> pure function: where does a price sit vs. thresholds?
    PriceMonitor    -> stateful wrapper that only raises an alert when the
                       state *changes*, so we don't spam the user every poll.

Keeping the monitor's state separate from classification makes both trivially
testable: classify() has no side effects, and the monitor's transition logic
can be exercised by feeding it a sequence of prices.
"""

from __future__ import annotations

from ..config import ThresholdConfig
from ..models import Alert, AlertLevel, PriceState, PricePoint


def classify(price_cents: float, thresholds: ThresholdConfig) -> PriceState:
    """Classify a price against the configured thresholds.

    At/above high_price_cents  -> EXPENSIVE
    At/below low_price_cents   -> CHEAP
    Otherwise                  -> NORMAL
    """
    if price_cents >= thresholds.high_price_cents:
        return PriceState.EXPENSIVE
    if price_cents <= thresholds.low_price_cents:
        return PriceState.CHEAP
    return PriceState.NORMAL


class PriceMonitor:
    """Tracks the current price state and emits alerts on transitions only.

    Example: if the price stays EXPENSIVE for an hour we alert once (when it
    crosses up), not twelve times. We re-alert when it changes to a new state.
    """

    def __init__(self, thresholds: ThresholdConfig) -> None:
        self._thresholds = thresholds
        # None until the first reading establishes a baseline.
        self._state: PriceState | None = None

    @property
    def state(self) -> PriceState | None:
        """The most recently observed price state (None before first update)."""
        return self._state

    def update(self, point: PricePoint) -> Alert | None:
        """Feed in the latest price; return an Alert only if the state changed.

        The very first reading sets the baseline state without alerting (we
        don't want a noisy alert the instant the service boots).
        """
        new_state = classify(point.price_cents, self._thresholds)
        previous = self._state
        self._state = new_state

        # First reading, or no change -> nothing to announce.
        if previous is None or new_state == previous:
            return None

        return self._build_alert(new_state, point)

    def _build_alert(self, state: PriceState, point: PricePoint) -> Alert | None:
        """Construct the user-facing alert for a transition into `state`."""
        price = point.price_cents
        if state == PriceState.EXPENSIVE:
            return Alert(
                level=AlertLevel.WARNING,
                title="High electricity price",
                message=(
                    f"Price rose to {price:.1f} cents/kWh "
                    f"(threshold {self._thresholds.high_price_cents:.1f}). "
                    "Consider holding off on the car and big appliances."
                ),
                created_at=point.timestamp,
            )
        if state == PriceState.CHEAP:
            return Alert(
                level=AlertLevel.INFO,
                title="Cheap electricity now",
                message=(
                    f"Price dropped to {price:.1f} cents/kWh "
                    f"(threshold {self._thresholds.low_price_cents:.1f}). "
                    "Good time to charge the car or run appliances."
                ),
                created_at=point.timestamp,
            )
        # Transition back into NORMAL: a quiet, informational "all clear".
        return Alert(
            level=AlertLevel.INFO,
            title="Electricity price back to normal",
            message=f"Price is now {price:.1f} cents/kWh.",
            created_at=point.timestamp,
        )
