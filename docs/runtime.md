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
- `DION_HARDWARE_REAL_ENDPOINTS`: JSON object for transport-specific endpoint values already supported by the hardware layer.
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
