from __future__ import annotations

from pathlib import Path

from app.application.composition import create_bootstrapped_application_container
from app.config import AppSettings
from app.domain.enums import StartupReadinessStatus
from app.hardware import HardwareFacade, MockDrumAdapter, MockLockAdapter, MockRfidAdapter


def test_container_builds_successfully_from_temp_sqlite_settings(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="composition.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )

    container = create_bootstrapped_application_container(settings)
    try:
        assert container.session is not None
        assert container.engine is not None
        assert container.session_factory is not None
    finally:
        container.close()


def test_all_expected_services_are_present(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="composition_services.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )

    container = create_bootstrapped_application_container(settings)
    try:
        assert container.services.auth is not None
        assert container.services.inventory is not None
        assert container.services.users is not None
        assert container.services.items is not None
        assert container.services.permissions is not None
        assert container.services.operation_sessions is not None
        assert container.services.dispense is not None
        assert container.services.return_ops is not None
        assert container.services.refill is not None
        assert container.services.recovery is not None
        assert container.services.service_mode is not None
        assert container.services.exports is not None
        assert container.services.startup is not None
    finally:
        container.close()


def test_startup_service_inside_container_can_run(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="composition_startup.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.database.ok is True
        assert result.recovery.ok is True
        assert result.readiness_status is StartupReadinessStatus.READY
    finally:
        container.close()


def test_operation_services_share_same_session_and_repository_base(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="composition_repos.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )

    container = create_bootstrapped_application_container(settings)
    try:
        assert container.repositories.operations.session is container.session
        assert container.repositories.inventory.session is container.session
        assert container.repositories.operation_sessions.session is container.session
        assert container.services.dispense.operation_repository.session is container.session
        assert container.services.return_ops.operation_repository.session is container.session
        assert container.services.refill.session_repository.session is container.session
        assert container.services.recovery.operation_repository.session is container.session
    finally:
        container.close()


def test_hardware_facade_is_wired_with_mock_adapters(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="composition_hardware.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )

    container = create_bootstrapped_application_container(settings)
    try:
        assert isinstance(container.hardware.facade, HardwareFacade)
        assert isinstance(container.hardware.drum_controller, MockDrumAdapter)
        assert isinstance(container.hardware.lock_controller, MockLockAdapter)
        assert isinstance(container.hardware.rfid_reader, MockRfidAdapter)
        assert container.services.service_mode.hardware_facade is container.hardware.facade
        assert container.services.startup.hardware_facade is container.hardware.facade
    finally:
        container.close()
