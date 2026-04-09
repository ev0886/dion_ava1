from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import AppSettings, HardwareProvider, get_settings
from app.hardware.transport_config import LockHardwareEndpointTransportConfig
from app.persistence.models import Slot


def bootstrap(settings: AppSettings | None = None) -> AppSettings:
    app_settings = settings or get_settings()
    app_settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_database_migrations(app_settings)
    align_runtime_slot_metadata(app_settings)
    return app_settings


def run_database_migrations(settings: AppSettings) -> None:
    alembic_config = Config(str(settings.alembic_config_path))
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_path = settings.alembic_config_path.resolve()
    alembic_config.set_main_option("script_location", str((alembic_path.parent / "alembic").resolve()))
    command.upgrade(alembic_config, "head")


def align_runtime_slot_metadata(settings: AppSettings) -> None:
    if settings.hardware_provider is not HardwareProvider.REAL:
        return

    raw_lock_config = settings.hardware_real_endpoints.get("lock_controller")
    if raw_lock_config is None:
        return

    try:
        lock_config = LockHardwareEndpointTransportConfig.model_validate(raw_lock_config)
    except ValidationError:
        return

    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
    )
    try:
        with Session(engine) as session:
            configured_board_address = lock_config.protocol.board_address
            slots = session.execute(select(Slot).where(Slot.board_address != configured_board_address)).scalars().all()
            if not slots:
                return
            for slot in slots:
                slot.board_address = configured_board_address
            session.commit()
    finally:
        engine.dispose()
