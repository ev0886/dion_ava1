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

## Hardware boundary readiness

Use this sequence when preparing the Raspberry Pi stand for the first non-mock hardware check:

1. Keep operation traffic off the stand. This step is only for `startup-check`, `hardware-health`, and `/readiness`.
2. Prefer `DION_HARDWARE_PROVIDER=real` when the goal is to verify actual endpoint reachability. In the current MVP, `stub-real` confirms provider wiring only and will stay degraded because the adapters are intentionally not implemented.
3. Set `DION_HARDWARE_REAL_ENDPOINTS` to a JSON object with the top-level keys `drum_controller`, `lock_controller`, and optionally `rfid_reader`.

Example shape:

```env
DION_HARDWARE_PROVIDER=real
DION_HARDWARE_REAL_ENDPOINTS={"drum_controller":{"endpoint":{"code":"drum-1","driver_name":"drum-driver","enabled":true,"timeouts":{"connect_timeout_ms":1000,"read_timeout_ms":1000,"write_timeout_ms":1000}},"transport":{"transport":"serial","port":"/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.2:1.0-port0","baudrate":9600,"data_bits":8,"parity":"none","stop_bits":1}},"lock_controller":{"endpoint":{"code":"lock-1","driver_name":"lock-driver","enabled":true,"timeouts":{"connect_timeout_ms":1000,"read_timeout_ms":1000,"write_timeout_ms":1000}},"protocol":{"board_address":0},"transport":{"transport":"serial","port":"/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.1:1.0-port0","baudrate":19200,"data_bits":8,"parity":"none","stop_bits":1}}}
```

Safe commands on the Pi:

```bash
python -m app.cli startup-check
python -m app.cli hardware-health
python -m app.api --startup-check-only
```

If the API is running, `/readiness` exposes the same startup readiness service. In `real` mode these checks stay read-only:

- `lock_controller`: CU24 query-version probe.
- `drum_controller`: GETPOS probe.
- `rfid_reader`: still not implemented for real mode in this MVP, so omit it or expect degraded readiness.

## Supported environment variables

- `DION_APP_NAME`: process title used by the API metadata and bootstrap message.
- `DION_APP_ENVIRONMENT`: descriptive environment label such as `development` or `production-like`.
- `DION_DATA_DIR`: directory for the SQLite file and local runtime artifacts.
- `DION_SQLITE_FILENAME`: SQLite database filename inside `DION_DATA_DIR`.
- `DION_ALEMBIC_CONFIG_PATH`: Alembic configuration file path.
- `DION_HARDWARE_PROVIDER`: `mock`, `stub-real`, or `real`.
- `DION_HARDWARE_REAL_ENDPOINTS`: JSON object keyed by `drum_controller`, `lock_controller`, and optional `rfid_reader`. `lock_controller` expects serial transport plus `protocol.board_address`.
- `DION_API_HOST`: bind address for `python -m app.api` and `dion-api`.
- `DION_API_PORT`: bind port for `python -m app.api` and `dion-api`.

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
