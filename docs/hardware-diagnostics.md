# Hardware Diagnostics Memo

Short practical commands for the live stand.

## Service status and logs

```bash
sudo systemctl status dion-api.service --no-pager
sudo journalctl -u dion-api.service -n 100 --no-pager
sudo journalctl -u dion-api.service -f
```

## Service restart flow

Use this order after config changes or a controlled restart:

```bash
sudo systemctl restart dion-api.service
sleep 2
sudo systemctl status dion-api.service --no-pager
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/readiness
cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
```

If the service does not come back cleanly, check:

- `journalctl -u dion-api.service -n 100 --no-pager`
- `/etc/default/dion_ava1`
- `/dev/serial/by-path`

## Hardware health

```bash
cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
```

Expected:

- exit code `0`
- all configured devices report available/healthy

## Serial ports and by-path mapping

```bash
ls -l /dev/serial/by-path
readlink -f /dev/serial/by-path/*
```

Use these commands to verify:

- which physical USB path maps to the drum controller
- which physical USB path maps to the CU24 lock controller
- whether a reboot or reconnection changed enumeration

Reminder:

- configure drum and lock using `/dev/serial/by-path/...`
- do not trust `ttyUSB0`/`ttyUSB1` ordering on the live stand

## Quick raw CU24 status probe

Board-wide status for the current baseline is:

- address `0`
- command `0x80`
- request packet `02 00 00 80 00 00 03 85`

Example raw probe against the configured CU24 serial port:

```bash
python3 - <<'PY'
import serial

port = "/dev/serial/by-path/<lock-controller-path>"
payload = bytes.fromhex("02 00 00 80 00 00 03 85")

with serial.Serial(port=port, baudrate=19200, bytesize=8, parity="N", stopbits=1, timeout=1) as ser:
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(payload)
    response = ser.read(64)
    print("request :", payload.hex(" "))
    print("response:", response.hex(" "))
PY
```

Interpret the response as:

- successful ACK code `0x10`
- 3 data bytes for the board-wide hook mask
- only controlled lock numbers should be used as authoritative application inputs

## Browser cache-bust and UI refresh

After deploy, restart, or static asset confusion, open the pages with a fresh query value:

```text
/ui/operator?v=20260422a
/ui/user?v=20260422a
```

Practical notes:

- change the `v=` suffix whenever you want to force a fresh browser fetch
- hard-refresh once after opening the new URL
- if kiosk Chromium still shows stale UI, restart the browser session and reopen the page with a new `v=` value
