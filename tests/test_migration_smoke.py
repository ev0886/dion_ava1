from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy import text

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
        "nomenclature_entries",
        "operations",
        "event_logs",
        "exports",
        "backups",
    }.issubset(table_names)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert "dispense_restriction_policy" in user_columns


def test_alembic_upgrade_normalizes_legacy_dispense_policy_names(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="migration_normalize.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    alembic_config = _alembic_config(settings)
    command.upgrade(alembic_config, "20260410_0002")

    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO roles (id, code, name) VALUES (1, 'user', 'User')"))
        connection.execute(
            text(
                """
                INSERT INTO users (role_id, user_code, full_name, status, is_active, dispense_restriction_policy)
                VALUES
                    (1, 'user-1', 'User One', 'active', 1, 'UNLIMITED'),
                    (1, 'user-2', 'User Two', 'active', 1, 'ONCE_PER_DAY'),
                    (1, 'user-3', 'User Three', 'active', 1, 'unlimited')
                """
            )
        )

    command.upgrade(alembic_config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT user_code, dispense_restriction_policy
                FROM users
                ORDER BY id ASC
                """
            )
        ).all()

    assert rows == [
        ("user-1", "unlimited"),
        ("user-2", "once_per_day"),
        ("user-3", "unlimited"),
    ]


def test_alembic_upgrade_backfills_active_items_for_existing_nomenclature(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="migration_nomenclature_backfill.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    alembic_config = _alembic_config(settings)
    command.upgrade(alembic_config, "20260421_0005")

    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO items (id, item_group_id, sku, name, description, unit, return_allowed, min_level, status)
                VALUES (1, NULL, 'item-1', 'Item One', NULL, 'pcs', 1, 0, 'active')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO nomenclature_entries (name, normalized_name, is_active)
                VALUES
                    ('Очки защитные', 'очки защитные', 1),
                    ('Перчатки защитные', 'перчатки защитные', 1)
                """
            )
        )

    command.upgrade(alembic_config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT sku, name, status
                FROM items
                ORDER BY id ASC
                """
            )
        ).all()

    assert rows == [
        ("item-1", "Item One", "active"),
        ("nomenclature-1", "Очки защитные", "active"),
        ("nomenclature-2", "Перчатки защитные", "active"),
    ]


def _alembic_config(settings: AppSettings) -> Config:
    alembic_config = Config(str(settings.alembic_config_path))
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_path = settings.alembic_config_path.resolve()
    alembic_config.set_main_option("script_location", str((alembic_path.parent / "alembic").resolve()))
    return alembic_config
