"""Process-level configuration, sourced from environment variables.

These are deployment knobs that don't change at runtime. Anything the user
should be able to tweak while the service runs (calibration, Brewer's Friend
key/toggle) lives in the database instead, editable from the web UI.
"""
import os

# Path to the SQLite database file. In Docker this lives on a mounted volume.
DB_PATH = os.environ.get("TILT_DB_PATH", "data/tilt.db")

# HTTP server bind address/port.
HOST = os.environ.get("TILT_HOST", "0.0.0.0")
PORT = int(os.environ.get("TILT_PORT", "8000"))

# When true, inject synthetic readings instead of scanning real BLE hardware.
# Lets the app run on a dev machine with no Tilt or working BlueZ stack.
SIMULATE = os.environ.get("TILT_SIMULATE", "").lower() in ("1", "true", "yes")

# BLE adapter to scan with (Linux/BlueZ), e.g. "hci0". Point this at a second
# USB Bluetooth dongle to keep the built-in radio free for other devices.
BLE_ADAPTER = os.environ.get("TILT_BLE_ADAPTER") or None

# "active" (default) or "passive". Passive scanning doesn't transmit scan
# requests and is much friendlier to other Bluetooth devices sharing the same
# adapter (e.g. a mouse). It's the natural fit since a Tilt only broadcasts.
# Passive mode needs BlueZ >= 5.56 with experimental features enabled.
SCAN_MODE = os.environ.get("TILT_SCAN_MODE", "active").lower()

# How often the Brewer's Friend uploader runs. Their Stream API enforces a
# 15-minute minimum, so don't lower this below 900 for real use.
UPLOAD_INTERVAL_SECONDS = int(os.environ.get("TILT_UPLOAD_INTERVAL", "900"))
