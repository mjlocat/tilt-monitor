"""FastAPI application: BLE scanner + Brewer's Friend uploader + web UI.

A single process runs background asyncio tasks (scanner, uploader) alongside
the HTTP server. Runtime settings (calibration, Brewer's Friend key/toggle)
live in SQLite and are edited from the dashboard.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .ble import SimulatedScanner, TiltScanner
from .db import Database
from .scheduler import run_uploader, upload_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("tilt-monitor")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(config.DB_PATH)
    await db.connect()
    app.state.db = db

    async def on_reading(reading: dict) -> None:
        await db.insert_reading(
            reading["color"],
            reading["temp_raw"],
            reading["sg_raw"],
            reading["tx_power"],
            reading["rssi"],
            reading["mac"],
        )

    if config.SIMULATE:
        log.info("Starting in SIMULATE mode (no real BLE scanning).")
        scanner = SimulatedScanner(on_reading)
    else:
        scanner = TiltScanner(
            on_reading, adapter=config.BLE_ADAPTER, scan_mode=config.SCAN_MODE
        )

    tasks = [
        asyncio.create_task(scanner.run(), name="scanner"),
        asyncio.create_task(
            run_uploader(db, config.UPLOAD_INTERVAL_SECONDS), name="uploader"
        ),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await db.close()


app = FastAPI(title="tilt-monitor", lifespan=lifespan)


class CalibrationUpdate(BaseModel):
    color: str
    temp_correction: float = 0.0
    sg_correction: float = 0.0


class SettingsUpdate(BaseModel):
    bf_enabled: bool | None = None
    bf_api_key: str | None = None


@app.get("/api/current")
async def api_current():
    return await app.state.db.current_readings()


@app.get("/api/history")
async def api_history(color: str, hours: float = 48):
    return await app.state.db.history(color, hours)


@app.get("/api/calibration")
async def api_get_calibration():
    cal = await app.state.db.all_calibration()
    return [
        {"color": c, "temp_correction": t, "sg_correction": s}
        for c, (t, s) in sorted(cal.items())
    ]


@app.put("/api/calibration")
async def api_put_calibration(update: CalibrationUpdate):
    await app.state.db.set_calibration(
        update.color, update.temp_correction, update.sg_correction
    )
    return {"ok": True}


@app.get("/api/settings")
async def api_get_settings():
    db = app.state.db
    return {
        "bf_enabled": (await db.get_setting("bf_enabled")) == "1",
        # Return whether a key is set, not the key itself.
        "bf_api_key_set": bool(await db.get_setting("bf_api_key")),
        "upload_interval_seconds": config.UPLOAD_INTERVAL_SECONDS,
    }


@app.put("/api/settings")
async def api_put_settings(update: SettingsUpdate):
    db = app.state.db
    if update.bf_enabled is not None:
        await db.set_setting("bf_enabled", "1" if update.bf_enabled else "0")
    if update.bf_api_key is not None:
        await db.set_setting("bf_api_key", update.bf_api_key)
    return {"ok": True}


@app.post("/api/brewersfriend/test")
async def api_bf_test():
    """Force an immediate upload attempt (useful for verifying setup)."""
    await upload_once(app.state.db, config.UPLOAD_INTERVAL_SECONDS)
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
