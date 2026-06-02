"""Live smoke test: run one real poll against ComEd + NWS and print the result.

This hits the real network (no mocks) to confirm the whole pipeline works
end to end. Run it with:  .venv/bin/python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio

import httpx

from home_auto.config import Config, LocationConfig
from home_auto.service import HomeAutoService


async def main() -> None:
    # Minimal in-code config (downtown Chicago) so we don't need a config.yaml.
    config = Config(location=LocationConfig(latitude=41.8781, longitude=-87.6298))

    async with httpx.AsyncClient(timeout=20.0) as http:
        service = HomeAutoService.build(config, http)
        await service.poll()

    snap = service.snapshot
    print("=== home-auto live smoke test ===")
    print(f"updated_at:        {snap.updated_at}")
    if snap.latest_price:
        print(
            f"latest price:      {snap.latest_price.price_cents} c/kWh "
            f"at {snap.latest_price.timestamp}"
        )
    print(f"price state:       {snap.price_state}")
    print(f"current hour avg:  {snap.current_hour_average} c/kWh")
    print(f"recent points:     {len(snap.recent_prices)}")
    if snap.charge_window:
        w = snap.charge_window
        print(
            f"charge window:     {w.start} -> {w.end} "
            f"(~{w.average_price_cents:.1f} c/kWh, {w.duration_hours}h)"
        )
    else:
        print("charge window:     none fits before deadline")
    if snap.weather and snap.weather.current:
        c = snap.weather.current
        print(f"weather:           {c.temperature}{c.temperature_unit} {c.short_forecast}")
    print(f"last error:        {snap.last_error}")


if __name__ == "__main__":
    asyncio.run(main())
