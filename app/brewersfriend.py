"""Brewer's Friend Stream API uploader.

Payload format ported from the original tilt2bf project. The Stream API is
rate-limited to a 15-minute minimum between posts per device.
"""
import httpx

STREAM_URL = "https://log.brewersfriend.com/stream/"


async def send_reading(api_key: str, color: str, temp, sg) -> int:
    """POST one averaged reading to Brewer's Friend. Returns HTTP status."""
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    }
    body = {
        "device_source": f"Tilt {color}",
        "report_source": "tilt-monitor",
        "name": f"Tilt {color}",
        "temp": temp,
        "temp_unit": "F",
        "gravity": sg,
        "gravity_unit": "G",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(STREAM_URL, headers=headers, json=body)
        return resp.status_code
