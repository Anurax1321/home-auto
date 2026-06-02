"""Entry point: `python -m home_auto`.

Wires everything together and runs two things in one event loop:
    1. An APScheduler job that calls service.poll() every interval_seconds.
    2. The uvicorn web server hosting the dashboard.

We do one poll immediately at startup so the dashboard has data right away,
then hand off to the scheduler for the recurring cycles.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import load_config
from .service import HomeAutoService
from .web.app import create_app

log = logging.getLogger("home_auto")


async def run() -> None:
    config = load_config()

    # One shared HTTP client for all outbound calls (connection reuse).
    http = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    service = HomeAutoService.build(config, http)
    app = create_app(service)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        service.poll,
        trigger="interval",
        seconds=config.polling.interval_seconds,
        max_instances=1,         # don't overlap polls if one runs long
        coalesce=True,           # collapse missed runs into one
    )

    # Prime the snapshot before serving so the first page load isn't empty.
    log.info("running initial poll…")
    await service.poll()
    scheduler.start()
    log.info(
        "polling every %ss; dashboard on http://%s:%s",
        config.polling.interval_seconds,
        config.dashboard.host,
        config.dashboard.port,
    )

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=config.dashboard.host,
            port=config.dashboard.port,
            log_level="info",
        )
    )
    try:
        await server.serve()
    finally:
        # Clean shutdown: stop the scheduler and close the HTTP client.
        scheduler.shutdown(wait=False)
        await http.aclose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
