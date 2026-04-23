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
- on a cloned SSD or new stand, drum and lock may be swapped relative to the old stand
- if `hardware-health` fails after cloning or USB changes, verify the physical drum and lock paths before editing config
- RFID may also need path verification if the reader moved from the configured ACM/serial path

## Runtime config spot check

```bash
grep -E 'DION_HARDWARE_PROVIDER|DION_HARDWARE_REAL_ENDPOINTS' /etc/default/dion_ava1
```

Expected:

- `DION_HARDWARE_PROVIDER=real`
- drum controller `port` is a `/dev/serial/by-path/...` value
- lock controller `port` is a `/dev/serial/by-path/...` value
- drum is not configured as `ttyUSB0` or `ttyUSB1`
- lock is not configured as `ttyUSB0` or `ttyUSB1`

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

## Drum timeout after failed move

Known symptom: after a failed drum move or mechanical jam, the drum controller may stop responding until the controller/mechanics are reset. This can appear as a drum timeout in `hardware-health`, readiness, or operation logs.

Use this decision path:

- If the drum is physically obstructed, noisy, or not reaching the target position, inspect and clear the mechanical jam before repeated retries.
- If mechanics are clear but the controller keeps timing out after one failed move, power-cycle the drum controller and restart `dion-api.service`.
- After any mechanical or power reset, run `hardware-health` before resuming operator/user flows.
- Do not mask repeated drum timeout errors with longer timeouts until the mechanical path and controller state have been checked.

Useful log check:

```bash
sudo journalctl -u dion-api.service -n 200 --no-pager | grep -Ei 'drum|timeout|hardware'
```

## RFID quick checks

```bash
ls -l /dev/serial/by-path
ls -l /dev/ttyACM*
cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
```

Checks:

- reader device exists at the configured path
- `hardware-health` reports the RFID endpoint available
- known active user, operator, and admin cards authenticate in the expected UI flows
- blocked or unknown cards show blocked-auth behavior

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
