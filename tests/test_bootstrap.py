from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap
from app.config import AppSettings, HardwareProvider
from app.domain.enums import SlotStatus, SlotType
from app.persistence.models import Slot


def test_bootstrap_runs_with_temp_sqlite(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="bootstrap.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )

    result = bootstrap(settings)

    assert result.sqlite_path.exists()


def test_bootstrap_realigns_real_slot_board_address_to_lock_controller_config(tmp_path: Path) -> None:
    sqlite_filename = "bootstrap_real_align.sqlite3"
    setup_settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )
    bootstrap(setup_settings)

    engine = create_engine(setup_settings.database_url, future=True, connect_args={"check_same_thread": False})
    try:
        with Session(engine) as session:
            session.add(
                Slot(
                    code="slot-1",
                    slot_type=SlotType.UNIVERSAL,
                    drum_position=1,
                    board_address=1,
                    lock_number=1,
                    capacity=10,
                    status=SlotStatus.ACTIVE,
                )
            )
            session.commit()
    finally:
        engine.dispose()

    real_settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "lock_controller": {
                "endpoint": {
                    "code": "lock-1",
                    "driver_name": "lock-driver",
                    "enabled": True,
                    "timeouts": {
                        "connect_timeout_ms": 1000,
                        "read_timeout_ms": 1000,
                        "write_timeout_ms": 1000,
                    },
                },
                "protocol": {"board_address": 0},
                "transport": {
                    "transport": "serial",
                    "port": "COM2",
                    "baudrate": 19200,
                    "data_bits": 8,
                    "parity": "none",
                    "stop_bits": 1,
                },
            }
        },
    )

    bootstrap(real_settings)

    verify_engine = create_engine(real_settings.database_url, future=True, connect_args={"check_same_thread": False})
    try:
        with Session(verify_engine) as session:
            slot = session.execute(select(Slot).where(Slot.code == "slot-1")).scalar_one()
            assert slot.board_address == 0
            assert slot.lock_number == 1
    finally:
        verify_engine.dispose()


def test_bootstrap_runs_from_non_repo_working_directory(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="bootstrap_cwd.sqlite3",
        alembic_config_path=Path(__file__).resolve().parents[1] / "alembic.ini",
    )
    outside_cwd = tmp_path / "outside-cwd"
    outside_cwd.mkdir()
    monkeypatch.chdir(outside_cwd)

    result = bootstrap(settings)

    assert result.sqlite_path.exists()
