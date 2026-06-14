# tilt-monitor

An always-on, Dockerized service that reads [Tilt Hydrometer](https://tilthydrometer.com/)
BLE broadcasts, stores them locally, shows live readings and historical graphs
in a web UI, and (optionally) forwards readings to
[Brewer's Friend](https://www.brewersfriend.com/).

This replaces the older two-script setup (`tilt2db` + `tilt2bf` + MySQL + cron).
Everything now runs in a single process with a single SQLite database.

## Features

- **Live dashboard** — current specific gravity, temperature, battery age, and
  signal strength for each Tilt color it sees.
- **Historical graphs** — gravity and temperature over a selectable time range.
- **In-browser calibration** — set per-color temperature/SG corrections; because
  raw readings are stored, changing a correction retroactively fixes the graphs.
- **Brewer's Friend toggle** — enable/disable 15-minute uploads and set the API
  key from the UI; no config edits or second cron job.
- **Portable** — uses [bleak](https://github.com/hbldh/bleak) (host BlueZ), so
  no custom `aioblescan` build is required.

## Screenshot

![tilt-monitor dashboard: a live reading card with calibration fields, the Brewer's Friend toggle, and a gravity/temperature history graph](https://raw.githubusercontent.com/mjlocat/tilt-monitor/main/docs/dashboard.png)

*The dashboard mid-fermentation (shown with sample data).*

## Run with Docker (recommended)

The image is published on Docker Hub as
[`mjlocat/tilt-monitor`](https://hub.docker.com/r/mjlocat/tilt-monitor). You can
pull it directly or build from source — either way the same host prerequisites
apply.

### Host prerequisites

The container runs as a non-root user (UID 1000) — it needs no elevated
privileges because the actual BLE work is done by the host's `bluetoothd` over
D-Bus. For that to work it needs `network_mode: host`, the system D-Bus socket
(`/var/run/dbus`) mounted, and membership in the host's `bluetooth` group so
D-Bus policy permits talking to BlueZ.

Two host-specific values to set before the first run:

- **`bluetooth` group GID.** D-Bus only lets root or the `bluetooth` group reach
  `org.bluez`. Find your host's GID and write it to a `.env` file next to the
  compose file (the compose default is `112`):

  ```sh
  echo "BLUETOOTH_GID=$(getent group bluetooth | cut -d: -f3)" >> .env
  ```

- **`./data` ownership.** The SQLite database persists in `./data` (mounted to
  `/data`). Since the container runs as UID 1000, make that directory writable
  by it:

  ```sh
  mkdir -p data && sudo chown -R 1000:1000 data
  ```

### Option A — pull from Docker Hub

Drop this `docker-compose.yml` next to the `.env` and `data` directory above:

```yaml
services:
  tilt-monitor:
    image: mjlocat/tilt-monitor:latest
    container_name: tilt-monitor
    restart: unless-stopped
    network_mode: host
    group_add:
      - "${BLUETOOTH_GID:-112}"
    volumes:
      - ./data:/data
      - /var/run/dbus:/var/run/dbus
    environment:
      - TILT_PORT=8000   # change if 8000 is already in use on the host
```

```sh
docker compose up -d
```

### Option B — build from source

```sh
git clone https://github.com/mjlocat/tilt-monitor.git && cd tilt-monitor
docker compose up -d --build
```

Either way, open `http://<host>:8000` (or whatever `TILT_PORT` you set).

## Run without Docker

```sh
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On Linux this scans via BlueZ; you may need to run with sufficient privileges
for BLE (e.g. `sudo`, or grant capabilities to the Python binary).

## Try it without a Tilt

Set `TILT_SIMULATE=1` to emit synthetic Red Tilt readings — useful for trying
the UI on a dev machine with no hardware or Bluetooth:

```sh
TILT_SIMULATE=1 uvicorn app.main:app
```

## Configuration

Deployment knobs are environment variables; everything you'd change while
brewing lives in the database and is edited from the web UI.

| Variable | Default | Description |
| --- | --- | --- |
| `TILT_DB_PATH` | `data/tilt.db` | SQLite file location |
| `TILT_HOST` / `TILT_PORT` | `0.0.0.0` / `8000` | HTTP bind address/port |
| `TILT_SIMULATE` | _(off)_ | `1` to emit synthetic readings |
| `TILT_BLE_ADAPTER` | _(auto)_ | BlueZ adapter, e.g. `hci0` / `hci1` |
| `TILT_SCAN_MODE` | `active` | `passive` to coexist better with other BT devices (see below) |
| `TILT_UPLOAD_INTERVAL` | `900` | Seconds between Brewer's Friend uploads (do not go below 900) |

## Bluetooth coexistence (mouse/keyboard won't connect)

A machine with a single Bluetooth radio time-shares it between scanning and
connections. Continuous *active* scanning can starve other devices (e.g. a BLE
mouse) of the airtime they need to connect. Options, best first:

1. **Dedicated adapter** — plug in a cheap USB Bluetooth dongle and point the
   service at it with `TILT_BLE_ADAPTER=hci1`, leaving the built-in radio free.
2. **Passive scanning** — set `TILT_SCAN_MODE=passive`. A Tilt only broadcasts,
   so passive mode is the natural fit and is much gentler on other devices. It
   requires BlueZ >= 5.56 with experimental features enabled (see below).
3. Use a non-Bluetooth (2.4 GHz dongle or wired) mouse/keyboard.

### Enabling BlueZ experimental features (for passive scanning)

Passive scanning uses BlueZ's `AdvertisementMonitorManager1` D-Bus interface,
which is gated behind experimental features and off by default. **Pick one** of
the two methods below (you don't need both), then restart and verify.

**Method A — `main.conf` (persistent, survives upgrades):**

```sh
sudo sed -i 's/^#\?Experimental = .*/Experimental = true/' /etc/bluetooth/main.conf
grep -n '^Experimental' /etc/bluetooth/main.conf   # should read: Experimental = true
sudo systemctl restart bluetooth
```

**Method B — systemd drop-in (leaves `main.conf` untouched):**

```sh
sudo systemctl edit bluetooth
```

Add, then save:

```ini
[Service]
ExecStart=
ExecStart=/usr/libexec/bluetooth/bluetoothd -E
```

```sh
sudo systemctl restart bluetooth
```

(The empty `ExecStart=` is required to clear the unit's original line before
setting the new one. Confirm the daemon path matches your distro; on Debian 13
it is `/usr/libexec/bluetooth/bluetoothd`.)

**Verify** the interface is now exposed:

```sh
busctl introspect org.bluez /org/bluez/hci0 | grep AdvertisementMonitorManager1
```

Note: restarting `bluetooth` briefly disconnects any connected Bluetooth devices.

## Brewer's Friend

Get a Premium API key from your
[Integrations page](https://www.brewersfriend.com/homebrew/profile/integrations),
paste it into the dashboard, and flip the toggle on. Readings (averaged over the
upload window, per color) post every 15 minutes. The Stream API enforces a
15-minute minimum, so don't lower `TILT_UPLOAD_INTERVAL`. You still need to link
the device to a brew session in Brewer's Friend for readings to appear on a graph.

## Calibration

Place the Tilt in plain water and compare: temperature should match a reference
thermometer and specific gravity should read `1.000`. Enter the offsets in the
card's calibration fields (e.g. temp correction `+1`, SG correction `-0.003`).

## No authentication

There is intentionally no login — keep this on a trusted LAN and do not expose
the port to the internet, since the UI can read/set the Brewer's Friend API key.

## Notes

- **Security:** the API key is stored in plain text in the SQLite DB.
- **Tilt Pro** higher-resolution broadcasts are auto-detected and decoded.
