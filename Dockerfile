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
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
