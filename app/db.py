"""SQLite persistence layer (async, via aiosqlite).

Design note: readings are stored *raw* (exactly as broadcast by the Tilt).
Calibration offsets are applied when data is read back for display or upload,
so adjusting calibration in the UI retroactively corrects historical graphs.
"""
import os
import time

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,            -- unix epoch seconds
    color     TEXT    NOT NULL,
    temp_raw  REAL    NOT NULL,            -- temperature as broadcast (deg F)
    sg_raw    REAL    NOT NULL,            -- specific gravity as broadcast
    tx_power  INTEGER,                     -- raw iBeacon tx byte; 0-152 = weeks since battery change
    rssi      INTEGER,
    mac       TEXT
);
CREATE INDEX IF NOT EXISTS idx_readings_color_ts ON readings (color, ts);

CREATE TABLE IF NOT EXISTS calibration (
    color           TEXT PRIMARY KEY,
    temp_correction REAL NOT NULL DEFAULT 0,
    sg_correction   REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_SETTINGS = {
    "bf_enabled": "0",
    "bf_api_key": "",
}


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # --- readings -------------------------------------------------------

    async def insert_reading(self, color, temp_raw, sg_raw, tx_power, rssi, mac):
        await self._conn.execute(
            "INSERT INTO readings (ts, color, temp_raw, sg_raw, tx_power, rssi, mac) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), color, temp_raw, sg_raw, tx_power, rssi, mac),
        )
        await self._conn.commit()

    async def current_readings(self) -> list[dict]:
        """Latest calibrated reading for each color seen."""
        cur = await self._conn.execute(
            """
            SELECT r.* FROM readings r
            JOIN (SELECT color, MAX(ts) AS ts FROM readings GROUP BY color) latest
              ON r.color = latest.color AND r.ts = latest.ts
            """
        )
        rows = await cur.fetchall()
        calibration = await self.all_calibration()
        result = []
        for row in rows:
            temp_c, sg_c = calibration.get(row["color"], (0.0, 0.0))
            result.append(
                {
                    "color": row["color"],
                    "ts": row["ts"],
                    "temperature": round(row["temp_raw"] + temp_c, 1),
                    "sg": round(row["sg_raw"] + sg_c, 4),
                    "battery_weeks": await self._battery_weeks(row["color"]),
                    "rssi": row["rssi"],
                    "mac": row["mac"],
                }
            )
        result.sort(key=lambda r: r["color"])
        return result

    async def _battery_weeks(self, color: str) -> int | None:
        """Most recent valid battery age (weeks) for a color.

        The Tilt alternates two packets and only one carries a real battery
        value (0-152); the other reports a fixed ~197. Pull the latest in-range
        value so the display stays steady instead of flickering between them.
        """
        cur = await self._conn.execute(
            "SELECT tx_power FROM readings "
            "WHERE color = ? AND tx_power BETWEEN 0 AND 152 "
            "ORDER BY ts DESC LIMIT 1",
            (color,),
        )
        row = await cur.fetchone()
        return row["tx_power"] if row else None

    async def history(self, color: str, hours: float) -> list[dict]:
        since = time.time() - hours * 3600
        cur = await self._conn.execute(
            "SELECT ts, temp_raw, sg_raw FROM readings "
            "WHERE color = ? AND ts >= ? ORDER BY ts",
            (color, since),
        )
        rows = await cur.fetchall()
        temp_c, sg_c = (await self.all_calibration()).get(color, (0.0, 0.0))
        return [
            {
                "ts": row["ts"],
                "temperature": round(row["temp_raw"] + temp_c, 1),
                "sg": round(row["sg_raw"] + sg_c, 4),
            }
            for row in rows
        ]

    async def average_since(self, color: str, since: float) -> dict | None:
        """Calibrated average temp/SG for a color over a time window."""
        cur = await self._conn.execute(
            "SELECT AVG(temp_raw) AS t, AVG(sg_raw) AS s, COUNT(*) AS n "
            "FROM readings WHERE color = ? AND ts >= ?",
            (color, since),
        )
        row = await cur.fetchone()
        if not row or row["n"] == 0:
            return None
        temp_c, sg_c = (await self.all_calibration()).get(color, (0.0, 0.0))
        return {
            "temperature": round(row["t"] + temp_c),
            "sg": round(row["s"] + sg_c, 3),
            "count": row["n"],
        }

    async def colors_since(self, since: float) -> list[str]:
        cur = await self._conn.execute(
            "SELECT DISTINCT color FROM readings WHERE ts >= ?", (since,)
        )
        return [row["color"] for row in await cur.fetchall()]

    # --- calibration ----------------------------------------------------

    async def all_calibration(self) -> dict[str, tuple[float, float]]:
        cur = await self._conn.execute(
            "SELECT color, temp_correction, sg_correction FROM calibration"
        )
        return {
            row["color"]: (row["temp_correction"], row["sg_correction"])
            for row in await cur.fetchall()
        }

    async def set_calibration(self, color, temp_correction, sg_correction):
        await self._conn.execute(
            """
            INSERT INTO calibration (color, temp_correction, sg_correction)
            VALUES (?, ?, ?)
            ON CONFLICT(color) DO UPDATE SET
                temp_correction = excluded.temp_correction,
                sg_correction = excluded.sg_correction
            """,
            (color, temp_correction, sg_correction),
        )
        await self._conn.commit()

    # --- settings -------------------------------------------------------

    async def get_setting(self, key: str) -> str | None:
        cur = await self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self._conn.commit()
