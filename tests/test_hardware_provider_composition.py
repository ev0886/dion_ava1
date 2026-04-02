from __future__ import annotations

from pathlib import Path

from app.application.composition import create_bootstrapped_application_container
from app.config import AppSettings, HardwareProvider
from app.domain.enums import StartupReadinessStatus
from app.hardware import (
    HardwareFacade,
    MockDrumAdapter,
    MockLockAdapter,
    MockRfidAdapter,
    StubRealDrumAdapter,
    StubRealLockAdapter,
    StubRealRfidAdapter,
    create_hardware_bundle,
)


def test_hardware_provider_selection_defaults_to_mock_and_supports_stub_real(tmp_path: Path) -> None:
    default_settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="provider_default.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )
    stub_real_settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="provider_stub_real.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.STUB_REAL,
    )

    default_bundle = create_hardware_bundle(default_settings)
    stub_real_bundle = create_hardware_bundle(stub_real_settings)

    assert default_bundle.provider is HardwareProvider.MOCK
    assert isinstance(default_bundle.drum_controller, MockDrumAdapter)
    assert isinstance(stub_real_bundle.provider, HardwareProvider)
    assert stub_real_bundle.provider is HardwareProvider.STUB_REAL
    assert isinstance(stub_real_bundle.drum_controller, StubRealDrumAdapter)


def test_mock_mode_composition_uses_mock_hardware_bundle(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="composition_mock.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.MOCK,
    )

    container = create_bootstrapped_application_container(settings)
    try:
        assert container.hardware.provider is HardwareProvider.MOCK
        assert isinstance(container.hardware.facade, HardwareFacade)
        assert isinstance(container.hardware.drum_controller, MockDrumAdapter)
        assert isinstance(container.hardware.lock_controller, MockLockAdapter)
        assert isinstance(container.hardware.rfid_reader, MockRfidAdapter)
        assert container.services.service_mode.hardware_facade is container.hardware.facade
        assert container.services.startup.hardware_facade is container.hardware.facade
    finally:
        container.close()


def test_stub_real_mode_composition_uses_stub_real_hardware_bundle(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="composition_stub_real.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.STUB_REAL,
    )

    container = create_bootstrapped_application_container(settings)
    try:
        assert container.hardware.provider is HardwareProvider.STUB_REAL
        assert isinstance(container.hardware.facade, HardwareFacade)
        assert isinstance(container.hardware.drum_controller, StubRealDrumAdapter)
        assert isinstance(container.hardware.lock_controller, StubRealLockAdapter)
        assert isinstance(container.hardware.rfid_reader, StubRealRfidAdapter)
        assert container.services.service_mode.hardware_facade is container.hardware.facade
        assert container.services.startup.hardware_facade is container.hardware.facade
    finally:
        container.close()


def test_readiness_differs_between_mock_and_stub_real_modes(tmp_path: Path) -> None:
    mock_settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="readiness_mock.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.MOCK,
    )
    stub_real_settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="readiness_stub_real.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.STUB_REAL,
    )

    mock_container = create_bootstrapped_application_container(mock_settings)
    stub_real_container = create_bootstrapped_application_container(stub_real_settings)
    try:
        mock_result = mock_container.services.startup.run_startup_checks()
        stub_real_result = stub_real_container.services.startup.run_startup_checks()

        assert mock_result.readiness_status is StartupReadinessStatus.READY
        assert mock_result.hardware.degraded is False

        assert stub_real_result.readiness_status is StartupReadinessStatus.DEGRADED
        assert stub_real_result.hardware.ok is True
        assert stub_real_result.hardware.degraded is True
        assert all(entry.is_available is False for entry in stub_real_result.hardware.entries)
        assert all(entry.message is not None for entry in stub_real_result.hardware.entries)
        assert any("not implemented" in (entry.message or "") for entry in stub_real_result.hardware.entries)
    finally:
        mock_container.close()
        stub_real_container.close()
