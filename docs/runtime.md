# Runtime and Deployment Notes

This project keeps one bootstrap path for both the API and CLI:

- `bootstrap()` creates the data directory and runs Alembic migrations.
- `create_app()` reuses that bootstrap path for API startup.
- `startup-check` and `--startup-check-only` reuse the existing readiness service.

## Local setup

1. Copy `.env.example` to `.env`.
2. Keep `DION_HARDWARE_PROVIDER=mock` unless you are intentionally testing another supported provider.
3. Start the API:

```bash
python -m app.api
```

4. Run a startup preflight without starting the API:

```bash
python -m app.api --startup-check-only
```

5. Run the operator CLI:

```bash
python -m app.cli startup-check
```

## Supported environment variables

- `DION_APP_NAME`: process title used by the API metadata and bootstrap message.
- `DION_APP_ENVIRONMENT`: descriptive environment label such as `development` or `production-like`.
- `DION_DATA_DIR`: directory for the SQLite file and local runtime artifacts.
- `DION_SQLITE_FILENAME`: SQLite database filename inside `DION_DATA_DIR`.
- `DION_ALEMBIC_CONFIG_PATH`: Alembic configuration file path.
- `DION_HARDWARE_PROVIDER`: `mock`, `stub-real`, or `real`.
- `DION_HARDWARE_REAL_ENDPOINTS`: JSON object for transport-specific endpoint values already supported by the hardware layer. For the current Raspberry Pi real-hardware baseline, keep `drum_controller.protocol.move_completion_timeout_ms=35000` and `drum_controller.protocol.post_move_unlock_delay_ms=3000`.
- `DION_API_HOST`: bind address for `python -m app.api` and `dion-api`.
- `DION_API_PORT`: bind port for `python -m app.api` and `dion-api`.

Example real-hardware endpoints JSON:

```json
{
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
      "port": "/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.2:1.0-port0",
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
      "port": "/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.1:1.0-port0",
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
      "port": "/dev/ttyACM0"
    }
  }
}
```

## Installed entry points

After installing the package, these console scripts are available:

- `dion-bootstrap`
- `dion-cli`
- `dion-api`

## Container helper

Build and run the minimal container helper:

```bash
docker build -t dion-aba1 .
docker run --rm -p 8000:8000 --env-file .env dion-aba1
```

The container helper is intentionally minimal. It does not add orchestration, secret management, or external services.

## Raspberry Pi desktop kiosk

For Raspberry Pi OS desktop kiosk/autostart setup that targets the existing `/ui/mvp` page, see `docs/raspberry-pi-kiosk.md` and the repo-managed assets in `deploy/raspberry-pi/`.

## Raspberry Pi OS deployment package

Production deployment packaging is intentionally narrow:

- target OS: clean Raspberry Pi OS
- target hardware: Raspberry Pi 5
- app path: `/opt/dion_ava1`
- systemd service: `dion-api.service`
- runtime env source of truth: `/etc/default/dion_ava1`

Repo-managed deployment assets:

- `deploy/raspberry-pi/install.sh`
- `deploy/raspberry-pi/update.sh`
- `deploy/raspberry-pi/dion_ava1.env.example`
- `deploy/raspberry-pi/dion-api.service`

### Fresh install on a clean Raspberry Pi OS machine

1. Clone the repo into `/opt/dion_ava1`.
2. Run:

```bash
cd /opt/dion_ava1
sudo bash deploy/raspberry-pi/install.sh
```

The install script is intended for Raspberry Pi OS on Raspberry Pi 5 only and performs:

- platform verification
- `apt` install of required system packages
- creation of `/opt/dion_ava1/var` and `/opt/dion_ava1/var/exports`
- creation or refresh of `/opt/dion_ava1/.venv`
- package install into the venv
- bootstrap plus Alembic migrations
- install of `dion-api.service`
- install of `/etc/default/dion_ava1` from the example only when the file is missing
- `systemctl daemon-reload`
- `systemctl enable --now dion-api.service`

### Update flow for an already deployed machine

After updating the checked-out repo contents already present on the machine, run:

```bash
cd /opt/dion_ava1
sudo bash deploy/raspberry-pi/update.sh
```

The update script performs:

- Raspberry Pi OS and Raspberry Pi 5 verification
- venv refresh and dependency reinstall from the current checkout
- bootstrap plus Alembic migrations
- refresh of the checked-in `dion-api.service`
- `systemctl daemon-reload`
- `systemctl restart dion-api.service`

It does not overwrite `/etc/default/dion_ava1`.

### Runtime env handling

Use `/etc/default/dion_ava1` as the runtime source of truth for the deployed service.

Rules for deployment:

- install copies the example file only if `/etc/default/dion_ava1` is missing
- install preserves an existing `/etc/default/dion_ava1`
- update preserves `/etc/default/dion_ava1`
- stand-specific hardware paths must be edited manually by a technician
- drum and lock must use `/dev/serial/by-path/...`
- drum and lock must not use `ttyUSB0` or `ttyUSB1`

Recommended post-install steps:

```bash
sudoedit /etc/default/dion_ava1
ls -l /dev/serial/by-path
readlink -f /dev/serial/by-path/*
sudo systemctl restart dion-api.service
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/readiness
cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
```

## Live stand stabilization docs

For the current live stand baseline and stabilization package, see:

- `docs/stand-smoke-checklist.md`
- `docs/runtime-baseline-rpi.md`
- `docs/hardware-diagnostics.md`

## Current operational baseline

The current DION ABA1 baseline is:

- user, operator, and admin web flows are working
- admin web auth is enabled at `/ui/admin`
- default admin login is `admin`
- default admin password is `dionava`
- admin password change is available in the admin web UI
- admin password reset over SSH is available with `python -m app.cli reset-admin-password`
- admin operations CSV export is available
- admin balances CSV export is available
- real hardware dispense is confirmed working
- operator prepare/replenish/remove hardware-assisted flow is confirmed working
- open-door safety is enabled
- operator execution idle timeout is 2 minutes
- operator UI shows filled-cell hints

Runtime configuration for real hardware must use `/dev/serial/by-path/...` for drum and lock controllers. Do not configure drum or lock as `ttyUSB0` or `ttyUSB1`.

## Numbering reference

Logical drum sector numbering is reverse-offset from the controller POS value:

```text
logical_sector = ((32 - POS) % 32) + 1
```

Examples:

- `POS 0 -> sector 1`
- `POS 31 -> sector 2`
- `POS 30 -> sector 3`
- `POS 1 -> sector 32`

Human cell numbering is:

```text
human_cell_number = ((logical_sector - 1) * 15) + lock_number
```

where `lock_number` is `1..15` inside the logical sector.

Operator quarter access positions are:

- `1/4 -> POS 26`
- `2/4 -> POS 18`
- `3/4 -> POS 10`
- `4/4 -> POS 2`
