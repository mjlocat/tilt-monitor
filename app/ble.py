"""BLE scanning and Tilt iBeacon decoding.

Replaces the old custom `aioblescan` fork + `tilt_decoder.py` with `bleak`,
which talks to the host BlueZ stack over D-Bus and is cross-platform. A
simulated scanner is provided for development without hardware.
"""
import asyncio
import random
from typing import Awaitable, Callable

from bleak import BleakScanner

# Apple's Bluetooth company identifier; Tilt broadcasts as an Apple iBeacon.
APPLE_COMPANY_ID = 0x004C

# iBeacon UUID (32 hex chars) -> Tilt color. (From the original tilt2db map.)
COLOR_MAP = {
    "a495bb10c5b14b44b5121370f02d74de": "Red",
    "a495bb20c5b14b44b5121370f02d74de": "Green",
    "a495bb30c5b14b44b5121370f02d74de": "Black",
    "a495bb40c5b14b44b5121370f02d74de": "Purple",
    "a495bb50c5b14b44b5121370f02d74de": "Orange",
    "a495bb60c5b14b44b5121370f02d74de": "Blue",
    "a495bb70c5b14b44b5121370f02d74de": "Yellow",
    "a495bb80c5b14b44b5121370f02d74de": "Pink",
}

# Reading is dict: color, temp_raw, sg_raw, tx_power, rssi, mac
OnReading = Callable[[dict], Awaitable[None]]


def decode_tilt(manufacturer_data: dict[int, bytes], rssi, mac) -> dict | None:
    """Parse a Tilt reading from BLE advertisement manufacturer data.

    Returns None if this advertisement is not a recognized Tilt.
    """
    payload = manufacturer_data.get(APPLE_COMPANY_ID)
    # iBeacon body: [0]=0x02 type, [1]=0x15 len, [2:18]=UUID, [18:20]=major,
    # [20:22]=minor, [22]=tx power (signed).
    if not payload or len(payload) < 23 or payload[0] != 0x02:
        return None

    uuid = payload[2:18].hex()
    color = COLOR_MAP.get(uuid)
    if color is None:
        return None

    major = int.from_bytes(payload[18:20], "big")
    minor = int.from_bytes(payload[20:22], "big")
    # The Tilt alternates two advertisements: one carries "weeks since battery
    # change" (0-152) in this byte, the other a fixed calibration value (197).
    # Read it unsigned; the >152 case is filtered out when displaying battery.
    tx_power = payload[22]

    # Tilt Pro broadcasts higher-resolution values (temp x10, SG x10000),
    # detectable by the much larger "minor" field.
    if minor > 5000:
        temp_raw = major / 10.0
        sg_raw = minor / 10000.0
    else:
        temp_raw = float(major)        # degrees F
        sg_raw = minor / 1000.0        # specific gravity

    return {
        "color": color,
        "temp_raw": temp_raw,
        "sg_raw": sg_raw,
        "tx_power": tx_power,          # weeks since battery change (std Tilt)
        "rssi": rssi,
        "mac": mac,
    }


class TiltScanner:
    """Continuously scans for Tilt advertisements via bleak."""

    def __init__(
        self,
        on_reading: OnReading,
        adapter: str | None = None,
        scan_mode: str = "active",
    ):
        self.on_reading = on_reading
        self.adapter = adapter
        self.scan_mode = scan_mode

    def _detection_callback(self, device, advertisement_data):
        reading = decode_tilt(
            advertisement_data.manufacturer_data,
            advertisement_data.rssi,
            device.address,
        )
        if reading:
            asyncio.create_task(self.on_reading(reading))

    def _passive_bluez_args(self):
        """BlueZ args restricting a passive scan to Tilt advertisements.

        Passive scanning on BlueZ requires an advertisement-monitor pattern.
        We match Apple manufacturer data (4c00) + iBeacon prefix (0215) + the
        Tilt UUID preamble (a495). Returns None if this bleak/platform can't.
        """
        try:
            from bleak.args.bluez import (
                AdvertisementDataType,
                BlueZScannerArgs,
                OrPattern,
            )
        except ImportError:
            return None
        pattern = OrPattern(
            0,
            AdvertisementDataType.MANUFACTURER_SPECIFIC_DATA,
            b"\x4c\x00\x02\x15\xa4\x95",
        )
        return BlueZScannerArgs(or_patterns=[pattern])

    async def run(self) -> None:
        kwargs = {"detection_callback": self._detection_callback}
        if self.adapter:
            kwargs["adapter"] = self.adapter
        if self.scan_mode == "passive":
            bluez = self._passive_bluez_args()
            if bluez is not None:
                kwargs["scanning_mode"] = "passive"
                kwargs["bluez"] = bluez
        scanner = BleakScanner(**kwargs)
        await scanner.start()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await scanner.stop()


class SimulatedScanner:
    """Emits synthetic Red Tilt readings so the app runs without hardware."""

    def __init__(self, on_reading: OnReading, interval: float = 5.0):
        self.on_reading = on_reading
        self.interval = interval

    async def run(self) -> None:
        temp = 68.0
        sg = 1.050
        while True:
            temp += random.uniform(-0.3, 0.3)
            sg += random.uniform(-0.0015, 0.0015)
            await self.on_reading(
                {
                    "color": "Red",
                    "temp_raw": float(round(temp)),
                    "sg_raw": round(sg, 3),
                    "tx_power": 6,
                    "rssi": -70,
                    "mac": "00:11:22:33:44:55",
                }
            )
            await asyncio.sleep(self.interval)
