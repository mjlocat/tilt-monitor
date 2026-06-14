# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`tilt-monitor`: an always-on service that scans for [Tilt Hydrometer](https://tilthydrometer.com/)
BLE advertisements, stores readings in SQLite, serves a web dashboard (live
values + historical graphs + calibration), and optionally forwards averaged
readings to the Brewer's Friend Stream API every 15 minutes.

It replaced an older design (two cron scripts `tilt2db`/`tilt2bf` + a custom
`aioblescan` fork + MySQL). The sibling `tilt2bf` repo is now deprecated.

## Running

```sh
# Dev, no hardware needed — emits synthetic Red Tilt readings:
TILT_SIMULATE=1 uvicorn app.main:app

# Real hardware (Linux/BlueZ); may need privileges for BLE:
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Docker (BLE needs host networking + D-Bus + NET_ADMIN; see docker-compose.yml):
docker compose up -d --build
```

No build step and no test suite. `pip install -r requirements.txt` to set up.

## Architecture

Single FastAPI process; `app/main.py` lifespan launches two background asyncio
tasks alongside the HTTP server:

- **Scanner** (`app/ble.py`) — `TiltScanner` uses `bleak.BleakScanner`; its
  detection callback runs `decode_tilt()` on each advertisement and persists raw
  readings. `SimulatedScanner` is the `TILT_SIMULATE` substitute. `decode_tilt`
  parses the Apple iBeacon (company id `0x004C`) and maps the UUID to a color
  via `COLOR_MAP`.
- **Uploader** (`app/scheduler.py`) — `run_uploader` loops every
  `UPLOAD_INTERVAL_SECONDS`; if `bf_enabled`, averages the last window per color
  and POSTs via `app/brewersfriend.py` (payload ported from old `tilt2bf`).

`app/db.py` (`Database`, aiosqlite) owns the schema and all queries.
`app/config.py` reads env-var deployment knobs. The UI is static files under
`app/static/` (vanilla JS + a vendored `chart.min.js` = luxon + Chart.js +
luxon adapter concatenated).

### Things worth knowing

- **Readings are stored raw; calibration is applied on read** (`Database.current_readings`,
  `history`, `average_since`). So editing a correction in the UI retroactively
  shifts historical graphs. Don't "fix" this by storing corrected values.
- **Tilt vs Tilt Pro**: `decode_tilt` treats `minor > 5000` as a Tilt Pro
  (temp = major/10, SG = minor/10000); otherwise temp = major °F, SG = minor/1000.
- **Battery**: the iBeacon tx-power byte carries "weeks since battery change" on
  a standard Tilt; surfaced as `battery_weeks`.
- **Runtime vs deploy config**: env vars (`config.py`) are deploy-time only;
  things the user changes while brewing (calibration, `bf_enabled`, `bf_api_key`)
  live in the `settings`/`calibration` tables and are edited from the UI.
- **No auth by design** — intended for a trusted LAN; the UI can read/set the BF
  API key. `GET /api/settings` returns `bf_api_key_set` (bool), never the key.
