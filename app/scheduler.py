"""Periodic Brewer's Friend upload loop.

Every interval, if uploads are enabled in settings, averages the last window
of readings per color and posts them. Mirrors the cadence the old tilt2bf
cron job used, but driven from inside the always-on service.
"""
import asyncio
import logging
import time

from . import brewersfriend
from .db import Database

log = logging.getLogger("tilt-monitor.scheduler")


async def upload_once(db: Database, interval_seconds: int) -> None:
    enabled = await db.get_setting("bf_enabled")
    if enabled != "1":
        return
    api_key = await db.get_setting("bf_api_key")
    if not api_key:
        log.warning("Brewer's Friend enabled but no API key set; skipping.")
        return

    since = time.time() - interval_seconds
    for color in await db.colors_since(since):
        avg = await db.average_since(color, since)
        if not avg:
            continue
        try:
            status = await brewersfriend.send_reading(
                api_key, color, avg["temperature"], avg["sg"]
            )
            log.info(
                "Uploaded %s: temp=%s sg=%s (n=%s) -> HTTP %s",
                color, avg["temperature"], avg["sg"], avg["count"], status,
            )
        except Exception as exc:  # network errors shouldn't kill the loop
            log.error("Brewer's Friend upload for %s failed: %s", color, exc)


async def run_uploader(db: Database, interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await upload_once(db, interval_seconds)
        except Exception as exc:
            log.error("Uploader iteration failed: %s", exc)
