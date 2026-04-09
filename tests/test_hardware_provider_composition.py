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
    RealDrumAdapter,
    RealLockAdapter,
    RealRfidAdapter,
    StubRealDrumAdapter,
    StubRealLockAdapter,
    StubRealRfidAdapter,
    create_hardware_bundle,
)
from app.hardware.factory import summarize_real_endpoint_configs


def test_hardware_provider_selection_defaults_to_mock_and_supports_stub_real_and_real(tmp_path: Path) -> None:
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
    real_settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="provider_real.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM2"),
        },
    )

    default_bundle = create_hardware_bundle(default_settings)
    stub_real_bundle = create_hardware_bundle(stub_real_settings)
    real_bundle = create_hardware_bundle(real_settings)

    assert default_bundle.provider is HardwareProvider.MOCK
    assert isinstance(default_bundle.drum_controller, MockDrumAdapter)
    assert isinstance(stub_real_bundle.provider, HardwareProvider)
    assert stub_real_bundle.provider is HardwareProvider.STUB_REAL
    assert isinstance(stub_real_bundle.drum_controller, StubRealDrumAdapter)
    assert real_bundle.provider is HardwareProvider.REAL
    assert isinstance(real_bundle.drum_controller, RealDrumAdapter)
    assert isinstance(real_bundle.lock_controller, RealLockAdapter)
    assert isinstance(real_bundle.rfid_reader, RealRfidAdapter)


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


def test_real_mode_with_invalid_or_incomplete_transport_config_fails_safely(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_invalid.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": {
                "endpoint": {
                    "code": "drum-1",
                    "driver_name": "drum-driver",
                },
                "transport": {
                    "transport": "serial",
                    "baudrate": 9600,
                },
            },
        },
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.readiness_status is StartupReadinessStatus.DEGRADED
        assert result.hardware.degraded is True
        assert all(entry.is_available is False for entry in result.hardware.entries)
        drum_entry = next(entry for entry in result.hardware.entries if entry.device_type == "drum_controller")
        assert drum_entry.message is not None
        assert "invalid" in drum_entry.message
        assert "transport.port" in drum_entry.message
        assert "DION_HARDWARE_REAL_ENDPOINTS" in drum_entry.message
    finally:
        container.close()


def test_real_mode_with_invalid_lock_board_address_fails_early_but_stays_degraded(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_invalid_lock_protocol.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(
                code="lock-1",
                driver_name="lock-driver",
                port="COM2",
                board_address=256,
            ),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM2"),
        },
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.readiness_status is StartupReadinessStatus.DEGRADED
        lock_entry = next(entry for entry in result.hardware.entries if entry.device_type == "lock_controller")
        assert lock_entry.is_available is False
        assert lock_entry.message is not None
        assert "protocol.board_address" in lock_entry.message
        assert "less than or equal to 255" in lock_entry.message
    finally:
        container.close()


def test_readiness_in_real_mode_is_still_degraded_without_working_real_transports(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_protocol_unavailable.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM2"),
        },
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.readiness_status is StartupReadinessStatus.DEGRADED
        assert result.hardware.ok is True
        assert result.hardware.degraded is True
        entries = {entry.device_type: entry for entry in result.hardware.entries}
        assert entries["drum_controller"].is_available is False
        assert entries["drum_controller"].message is not None
        assert any(entry.is_available is False for entry in entries.values())
        assert result.message is not None
        assert "hardware degraded" in result.message
    finally:
        container.close()


def test_real_endpoint_config_summary_reports_unexpected_keys_and_targets(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_summary.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="/dev/ttyUSB0"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="/dev/ttyUSB1"),
            "unused_endpoint": {},
        },
    )

    summary = summarize_real_endpoint_configs(settings)

    assert len(summary.entries) == 3
    assert summary.warnings
    assert "unused_endpoint" in summary.warnings[0]
    drum_entry = next(entry for entry in summary.entries if entry.endpoint_name == "drum_controller")
    assert drum_entry.transport == "serial"
    assert drum_entry.target == "/dev/ttyUSB0"
    lock_entry = next(entry for entry in summary.entries if entry.endpoint_name == "lock_controller")
    assert lock_entry.transport == "serial"
    assert lock_entry.target == "/dev/ttyUSB1"


def _serial_endpoint_config(*, code: str, driver_name: str, port: str) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 9600,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }


def _lock_serial_endpoint_config(*, code: str, driver_name: str, port: str, board_address: int = 0) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "protocol": {
            "board_address": board_address,
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 19200,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }
