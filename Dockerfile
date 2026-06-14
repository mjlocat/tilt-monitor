FROM python:3.12-slim

# BlueZ tooling for BLE access via the host D-Bus/Bluetooth stack.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bluez \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV TILT_DB_PATH=/data/tilt.db \
    TILT_PORT=8000
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
