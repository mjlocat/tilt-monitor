FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user. The app needs no elevated privileges: BLE scanning is
# performed by the host's bluetoothd over D-Bus (bleak talks to it via the
# dbus-fast library, so no in-container BlueZ tooling is needed either), and the
# only writable path is the data volume.
RUN groupadd -g 1000 tilt \
    && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin tilt \
    && mkdir -p /data && chown tilt:tilt /data
USER tilt

ENV TILT_DB_PATH=/data/tilt.db \
    TILT_PORT=8000
VOLUME ["/data"]
# Informational only (the default port); set TILT_PORT to change the bind port.
# Note: docker-compose uses host networking, so this maps nothing — the service
# binds directly to TILT_PORT on the host.
EXPOSE 8000

# Honors TILT_HOST / TILT_PORT via app/config.py (see app/__main__.py).
CMD ["python", "-m", "app"]
