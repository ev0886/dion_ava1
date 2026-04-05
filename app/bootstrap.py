from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import AppSettings, get_settings


def bootstrap(settings: AppSettings | None = None) -> AppSettings:
    app_settings = settings or get_settings()
    app_settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_database_migrations(app_settings)
    return app_settings


def run_database_migrations(settings: AppSettings) -> None:
    alembic_config = Config(str(settings.alembic_config_path))
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_path = settings.alembic_config_path.resolve()
    alembic_config.set_main_option("script_location", str((alembic_path.parent / "alembic").resolve()))
    command.upgrade(alembic_config, "head")
