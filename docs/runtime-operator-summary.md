# Runtime Operator Summary

This repository is currently oriented around the backend MVP freeze.

Supported runtime paths:

- `python -m app.main`
  Runs bootstrap only: creates the data directory if needed and applies Alembic migrations.
- `app.api.create_app(...)`
  Creates the FastAPI application with `/health`, `/readiness`, auth, inventory, operations, recovery, service-mode, and export routes.
- `python -m app.cli --help`
  Shows the supported operator CLI commands for startup checks, hardware health, recovery scan, service-mode open/close, and export planning.

Runtime/auth expectations:

- The API keeps the current route set and returns JSON payloads from the existing service layer.
- Protected business actions rely on the application services for authorization checks.
- Service-mode open/close requires an operator or admin user through the existing auth rules.

Hardware modes:

- `mock`
  Default for local development and tests.
- `stub-real`
  Keeps the real-provider composition shape while using stubbed adapters.
- `real`
  Uses configured transport endpoints for drum, lock, and RFID integrations.

Key settings:

- `DION_DATA_DIR`
- `DION_SQLITE_FILENAME`
- `DION_ALEMBIC_CONFIG_PATH`
- `DION_HARDWARE_PROVIDER`
- `DION_HARDWARE_REAL_ENDPOINTS`

Recommended smoke path before release:

1. `python -m app.cli startup-check`
2. `python -m app.cli hardware-health`
3. `python -m app.cli recovery-scan`
4. `python -m pytest`
