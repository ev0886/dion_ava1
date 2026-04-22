# Runtime Baseline For Live RPi Stand

This document describes the currently working live-stand runtime baseline. It is a stabilization note, not a feature spec.

## Service and repo location

- systemd service: `dion-api.service`
- expected repo path on Raspberry Pi: `/opt/dion_ava1`
- expected API bind: `127.0.0.1:8000` unless overridden in `/etc/default/dion_ava1`
- service entrypoint: `python -m app.api`

The checked-in unit file is `deploy/raspberry-pi/dion-api.service` and loads `/etc/default/dion_ava1`.

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
- admin web nomenclature flow is part of the confirmed baseline
- operator replenish/remove flows are confirmed working
- operator prepare must finish quarter-positioning before final confirm
- user dispense is confirmed on real hardware
- success screen after real dispense is confirmed working
- blocked-auth and blocked-user messaging are confirmed working

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
