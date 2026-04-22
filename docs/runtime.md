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

## Live stand stabilization docs

For the current live stand baseline and stabilization package, see:

- `docs/stand-smoke-checklist.md`
- `docs/runtime-baseline-rpi.md`
- `docs/hardware-diagnostics.md`
