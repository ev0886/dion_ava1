from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.bootstrap import run_database_migrations
from app.config import AppSettings


def test_alembic_upgrade_creates_core_tables(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="migration.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    run_database_migrations(settings)

    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert {
        "roles",
        "users",
        "items",
        "slots",
        "operations",
        "event_logs",
        "exports",
        "backups",
    }.issubset(table_names)
