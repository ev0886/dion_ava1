# Runtime Baseline For Live RPi Stand

This document describes the currently working live-stand runtime baseline. It is a stabilization note, not a feature spec.

## Service and repo location

- systemd service: `dion-api.service`
- expected repo path on Raspberry Pi: `/opt/dion_ava1`
- expected API bind: `127.0.0.1:8000` unless overridden in `/etc/default/dion_ava1`
- service entrypoint: `python -m app.api`
- runtime env file: `/etc/default/dion_ava1`

For a clean Raspberry Pi OS deployment on Raspberry Pi 5, use:

- install script: `deploy/raspberry-pi/install.sh`
- update script: `deploy/raspberry-pi/update.sh`
- env template source: `deploy/raspberry-pi/dion_ava1.env.example`

The checked-in unit file is `deploy/raspberry-pi/dion-api.service` and loads `/etc/default/dion_ava1`.

## Clean Raspberry Pi OS install path

Use this flow on a fresh Raspberry Pi OS image for a new machine:

```bash
sudo mkdir -p /opt
cd /opt
sudo git clone <repo-url> dion_ava1
cd /opt/dion_ava1
sudo bash deploy/raspberry-pi/install.sh
sudoedit /etc/default/dion_ava1
sudo systemctl restart dion-api.service
cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
```

What the install script does:

- verifies Raspberry Pi OS and Raspberry Pi 5
- expects the repo to already live at `/opt/dion_ava1`
- installs required system packages for this deployment baseline
- creates `/opt/dion_ava1/var` and `/opt/dion_ava1/var/exports`
- creates or refreshes `/opt/dion_ava1/.venv`
- installs the project into the venv
- runs bootstrap and Alembic migrations
- installs the checked-in `dion-api.service`
- installs `/etc/default/dion_ava1` only when missing
- enables and starts `dion-api.service`

## Update path on an existing deployed stand

After the repo already present on the machine has been updated in place, run:

```bash
cd /opt/dion_ava1
sudo bash deploy/raspberry-pi/update.sh
```

What the update script does:

- verifies Raspberry Pi OS and Raspberry Pi 5
- refreshes `/opt/dion_ava1/.venv`
- reinstalls the current project and dependencies
- runs bootstrap and Alembic migrations
- refreshes the systemd unit from the repo
- reloads systemd
- restarts `dion-api.service`

What it preserves:

- existing `/etc/default/dion_ava1`
- existing stand-specific hardware path configuration
- current operator, user, and admin behavior

## Real hardware transport baseline

Use:

- `DION_HARDWARE_PROVIDER=real`
- `DION_HARDWARE_REAL_ENDPOINTS=...` JSON from `/etc/default/dion_ava1`

Expected transport approach:

- drum controller over serial
- CU24 lock controller over serial
- RFID reader over serial

For the stable live stand, drum and lock ports must be configured by `/dev/serial/by-path/...` names, not by `ttyUSB0` or `ttyUSB1`.

Why `by-path` is required:

- `ttyUSB0` and `ttyUSB1` can swap after reboot, reconnect, or USB enumeration changes
- the stand has been stable only when drum and lock ports are pinned to physical USB path identities
- `by-path` preserves the mapping from the exact USB topology to the configured controller

RFID may still appear as a different device class such as `/dev/ttyACM0`, but the stand-specific path should still be verified on hardware.

## Cloned SSD or new stand bring-up

Use this sequence after booting a cloned SSD on a new stand, after moving USB cables, or after replacing controller hardware:

1. Confirm the repo and service location:

```bash
cd /opt/dion_ava1
sudo systemctl status dion-api.service --no-pager
```

2. List serial identities:

```bash
ls -l /dev/serial/by-path
readlink -f /dev/serial/by-path/*
```

3. Check the configured runtime paths:

```bash
grep -E 'DION_HARDWARE_PROVIDER|DION_HARDWARE_REAL_ENDPOINTS' /etc/default/dion_ava1
```

4. Restart and run readiness plus hardware diagnostics:

```bash
sudo systemctl restart dion-api.service
sleep 2
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/readiness
.venv/bin/python -m app.cli hardware-health
```

On a cloned SSD or new stand, drum and lock USB paths may be swapped relative to the previous stand. If `hardware-health` shows one controller failing or the behavior does not match the intended device, swap only the drum and lock `port` values in `/etc/default/dion_ava1`, restart the service, and run `hardware-health` again. Do not switch to `ttyUSB0` or `ttyUSB1`.

RFID may also need path verification. Check whether the reader is still the configured ACM/serial device and update only after confirming the physical reader path.

## Current CU24 assumptions

- `board_address = 0`
- serial line is `19200 8N1`
- board-wide polling uses command `0x80`
- board-wide status payload is a 3-byte hook mask
- only controlled lock numbers are authoritative for application decisions

Interpretation note:

- the 3-byte CU24 payload is a 24-bit little-endian hook/closed mask
- a bit value of `1` means the corresponding physical lock is closed/hooked
- application logic must treat only configured/controlled lock numbers as relevant; unrelated cells on the same board are not authoritative for the stand workflow

## Drum and lock safety assumptions

- door/lock checks are part of the live baseline and must stay enabled
- open-door safety must block or warn as already implemented
- quarter-positioning before operator confirm is part of the accepted operator baseline
- this package does not change any hardware protocol, timing model, or safety rule

## User and operator flow notes

- RFID auth by role is part of the confirmed baseline
- admin web auth and nomenclature flow are part of the confirmed baseline
- admin web default login is `admin`, default password is `dionava`
- admin web password change is available in the UI
- admin password reset over SSH is `cd /opt/dion_ava1 && .venv/bin/python -m app.cli reset-admin-password`
- admin operations CSV export is available
- admin balances CSV export is available
- operator replenish/remove flows are confirmed working
- operator prepare must finish quarter-positioning before final confirm
- operator quarter access POS mapping is `1/4 -> 26`, `2/4 -> 18`, `3/4 -> 10`, `4/4 -> 2`
- corrected logical sector and human cell numbering are in place
- operator execution screen idle timeout is 2 minutes
- operator filled-cell hint is present
- user dispense is confirmed on real hardware
- user dispense logical numbering is fixed
- success screen after real dispense is confirmed working
- blocked-auth and blocked-user messaging are confirmed working

## Admin web quick reference

- Open `/ui/admin`.
- Login is required before admin pages and admin CSV exports are usable.
- Default credentials are `admin` / `dionava`.
- Change the password from the admin web UI after first login.
- If the password is lost, reset it over SSH:

```bash
cd /opt/dion_ava1
.venv/bin/python -m app.cli reset-admin-password
```

After reset, login again with `admin` / `dionava` and set a new password in the UI.

Exports:

- Operations CSV: admin web operations export by date range.
- Balances CSV: admin web balances export.
- Admin touch USB operations export: `/ui/admin-touch` writes operations CSV to the mounted USB device.
- Admin touch USB balances export: `/ui/admin-touch` writes balances CSV to the mounted USB device.

First-use admin step on a fresh Raspberry Pi OS install:

- after the service is healthy, open `/ui/admin`
- login with the current baseline credentials
- change the admin password before production handover

## Logical numbering reference

Logical sector numbering:

```text
sector = ((32 - POS) % 32) + 1
```

Examples:

- `POS 0 -> sector 1`
- `POS 31 -> sector 2`
- `POS 30 -> sector 3`
- `POS 1 -> sector 32`

Human cell numbering:

```text
human_cell_number = ((logical_sector - 1) * 15) + lock_number
```

where `lock_number` is `1..15`.

## Runtime config baseline for `/etc/default/dion_ava1`

Use the pattern below and replace the `by-path` values with the exact stand-specific paths from `ls -l /dev/serial/by-path`.

```bash
DION_HARDWARE_PROVIDER=real
DION_API_HOST=127.0.0.1
DION_API_PORT=8000
DION_HARDWARE_REAL_ENDPOINTS='{
  "drum_controller": {
    "endpoint": {
      "code": "drum-1",
      "driver_name": "drum-driver",
      "enabled": true,
      "timeouts": {
        "connect_timeout_ms": 1000,
        "read_timeout_ms": 1000,
        "write_timeout_ms": 1000
      }
    },
    "protocol": {
      "move_completion_timeout_ms": 35000,
      "post_move_unlock_delay_ms": 3000
    },
    "transport": {
      "transport": "serial",
      "port": "/dev/serial/by-path/<drum-controller-path>",
      "baudrate": 9600,
      "data_bits": 8,
      "parity": "none",
      "stop_bits": 1
    }
  },
  "lock_controller": {
    "endpoint": {
      "code": "lock-1",
      "driver_name": "lock-driver",
      "enabled": true,
      "timeouts": {
        "connect_timeout_ms": 1000,
        "read_timeout_ms": 1000,
        "write_timeout_ms": 1000
      }
    },
    "protocol": {
      "board_address": 0
    },
    "transport": {
      "transport": "serial",
      "port": "/dev/serial/by-path/<lock-controller-path>",
      "baudrate": 19200,
      "data_bits": 8,
      "parity": "none",
      "stop_bits": 1
    }
  },
  "rfid_reader": {
    "endpoint": {
      "code": "rfid-1",
      "driver_name": "rfid-driver",
      "enabled": true,
      "timeouts": {
        "connect_timeout_ms": 1000,
        "read_timeout_ms": 1000,
        "write_timeout_ms": 1000
      }
    },
    "transport": {
      "transport": "serial",
      "port": "/dev/ttyACM0",
      "baudrate": 9600,
      "data_bits": 8,
      "parity": "none",
      "stop_bits": 1
    }
  }
}'
```

Important:

- exact `by-path` values are machine-specific
- verify them on the live stand before restart
- do not replace drum or lock with `ttyUSB0`/`ttyUSB1` shortcuts
