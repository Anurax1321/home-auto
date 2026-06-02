"""Client for the ComEd Hourly Pricing API.

ComEd (the Illinois utility) publishes a free, no-auth JSON feed of the
real-time wholesale energy-supply price. Docs: https://hourlypricing.comed.com/hp-api/

Endpoints we use (all under https://hourlypricing.comed.com/api):
    ?type=5minutefeed        -> list of the last ~24h of 5-minute prices
    ?type=currenthouraverage -> single value: the running average for this hour
    ?type=5minutefeed&datestart=YYYYMMDDHHMM&dateend=YYYYMMDDHHMM
                             -> 5-minute prices for an explicit UTC range (history)

Each price entry looks like: {"millisUTC": "1780340700000", "price": "2.8"}
where price is US cents per kWh and millisUTC is the epoch in milliseconds.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import PricePoint

# Base URL for all ComEd Hourly Pricing API calls.
API_BASE = "https://hourlypricing.comed.com/api"

# ComEd expects/returns timestamps in UTC milliseconds. The datestart/dateend
# query params use this compact format.
_RANGE_FMT = "%Y%m%d%H%M"


def _parse_points(raw: list[dict]) -> list[PricePoint]:
    """Convert ComEd's raw JSON entries into sorted PricePoint objects.

    The API returns newest-first; we sort oldest-first so downstream code
    (graphs, profiles) can assume chronological order. Malformed entries are
    skipped rather than crashing the whole poll.
    """
    points: list[PricePoint] = []
    for entry in raw:
        try:
            millis = int(entry["millisUTC"])
            price = float(entry["price"])
        except (KeyError, ValueError, TypeError):
            # Skip a bad row but keep the rest of the feed usable.
            continue
        ts = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
        points.append(PricePoint(timestamp=ts, price_cents=price))

    points.sort(key=lambda p: p.timestamp)
    return points


class ComEdClient:
    """Async client for the ComEd Hourly Pricing API.

    Pass in an httpx.AsyncClient so callers (and tests) control the transport,
    timeouts, and lifecycle. Nothing here keeps state between calls.
    """

    def __init__(self, http: httpx.AsyncClient, base_url: str = API_BASE) -> None:
        self._http = http
        self._base_url = base_url

    async def get_5min_feed(self) -> list[PricePoint]:
        """Return the last ~24 hours of 5-minute prices, oldest first."""
        resp = await self._http.get(self._base_url, params={"type": "5minutefeed"})
        resp.raise_for_status()
        return _parse_points(resp.json())

    async def get_current_hour_average(self) -> float:
        """Return the running average price for the current hour, in cents/kWh."""
        resp = await self._http.get(
            self._base_url, params={"type": "currenthouraverage"}
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            raise ValueError("ComEd currenthouraverage returned no data")
        return float(data[0]["price"])

    async def get_latest_price(self) -> PricePoint:
        """Return the single most recent 5-minute price point."""
        feed = await self.get_5min_feed()
        if not feed:
            raise ValueError("ComEd 5minutefeed returned no data")
        return feed[-1]  # feed is sorted oldest-first

    async def get_history(
        self, start: datetime, end: datetime
    ) -> list[PricePoint]:
        """Return 5-minute prices for an explicit time range, oldest first.

        `start`/`end` may be naive or aware; they are converted to UTC for the
        query because ComEd interprets the range in UTC.
        """
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        resp = await self._http.get(
            self._base_url,
            params={
                "type": "5minutefeed",
                "datestart": start_utc.strftime(_RANGE_FMT),
                "dateend": end_utc.strftime(_RANGE_FMT),
            },
        )
        resp.raise_for_status()
        return _parse_points(resp.json())
