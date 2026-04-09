from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import AppSettings, HardwareProvider, get_settings
from app.domain.enums import SlotStatus, SlotType
from app.hardware.transport_config import LockHardwareEndpointTransportConfig
from app.persistence.models import Slot

REAL_MACHINE_DRUM_POSITIONS = range(32)
REAL_MACHINE_LOCK_NUMBERS = range(1, 16)
REAL_MACHINE_BOARD_ADDRESS = 0


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

    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
    )
    try:
        with Session(engine) as session:
            configured_board_address = _resolve_runtime_board_address(settings)
            slots = session.execute(select(Slot).order_by(Slot.id.asc())).scalars().all()
            slots_by_position = {(slot.drum_position, slot.lock_number): slot for slot in slots}
            changed = False

            for drum_position in REAL_MACHINE_DRUM_POSITIONS:
                for lock_number in REAL_MACHINE_LOCK_NUMBERS:
                    slot = slots_by_position.get((drum_position, lock_number))
                    if slot is None:
                        session.add(
                            Slot(
                                code=_runtime_slot_code(drum_position=drum_position, lock_number=lock_number),
                                slot_type=SlotType.UNIVERSAL,
                                drum_position=drum_position,
                                board_address=configured_board_address,
                                lock_number=lock_number,
                                capacity=None,
                                status=SlotStatus.ACTIVE,
                            )
                        )
                        changed = True
                        continue

                    if slot.board_address != configured_board_address:
                        slot.board_address = configured_board_address
                        changed = True

            if changed:
                session.commit()
    finally:
        engine.dispose()


def _resolve_runtime_board_address(settings: AppSettings) -> int:
    raw_lock_config = settings.hardware_real_endpoints.get("lock_controller")
    if raw_lock_config is None:
        return REAL_MACHINE_BOARD_ADDRESS

    try:
        lock_config = LockHardwareEndpointTransportConfig.model_validate(raw_lock_config)
    except ValidationError:
        return REAL_MACHINE_BOARD_ADDRESS

    return lock_config.protocol.board_address


def _runtime_slot_code(*, drum_position: int, lock_number: int) -> str:
    return f"slot-p{drum_position:02d}-l{lock_number:02d}"
