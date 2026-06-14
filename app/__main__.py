"""Entry point: `python -m app`.

Launches uvicorn binding to the host/port from config (TILT_HOST/TILT_PORT),
so those settings are honored rather than hardcoded at the container level.
"""
import uvicorn

from . import config

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)
