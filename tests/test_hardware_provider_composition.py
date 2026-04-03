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
            "lock_controller": _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="127.0.0.1", port=9001),
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

        assert result.readiness_status is StartupReadinessStatus.NOT_READY
        assert result.hardware.ok is False
        assert result.hardware.degraded is False
        assert result.hardware.critical_failures == ("drum_controller", "lock_controller")
        drum_entry = next(entry for entry in result.hardware.entries if entry.device_type == "drum_controller")
        assert drum_entry.message is not None
        assert "invalid" in drum_entry.message
        assert "transport.serial.port" in drum_entry.message
        assert drum_entry.status.value == "unavailable"
    finally:
        container.close()


def test_real_mode_with_obviously_invalid_tcp_host_fails_early_and_is_not_ready(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_invalid_host.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="0.0.0.0", port=9001),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM2"),
        },
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.readiness_status is StartupReadinessStatus.NOT_READY
        lock_entry = next(entry for entry in result.hardware.entries if entry.device_type == "lock_controller")
        assert lock_entry.is_available is False
        assert lock_entry.message is not None
        assert "transport.tcp.host" in lock_entry.message
        assert "reachable remote host" in lock_entry.message
    finally:
        container.close()


def test_readiness_in_real_mode_is_not_ready_without_working_critical_real_transports(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_protocol_unavailable.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="127.0.0.1", port=9001),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM2"),
        },
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.readiness_status is StartupReadinessStatus.NOT_READY
        assert result.hardware.ok is False
        assert result.hardware.degraded is False
        assert result.hardware.critical_failures == ("drum_controller", "lock_controller")
        entries = {entry.device_type: entry for entry in result.hardware.entries}
        assert entries["drum_controller"].is_available is False
        assert entries["drum_controller"].message is not None
        assert any(entry.is_available is False for entry in entries.values())
    finally:
        container.close()


def test_readiness_in_real_mode_is_degraded_when_only_non_critical_rfid_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.hardware import factory as hardware_factory

    class _FakeTransport:
        def __init__(self, response: bytes) -> None:
            self._response = response

        def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
            return self._response

    def fake_create_transport_client(config):
        if config is None:
            return None
        if config.endpoint.code == "rfid-1":
            return None
        return _FakeTransport(b"PONG\n")

    monkeypatch.setattr(hardware_factory, "_create_transport_client", fake_create_transport_client)

    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_rfid_degraded.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="127.0.0.1", port=9001),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM2"),
        },
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.readiness_status is StartupReadinessStatus.DEGRADED
        assert result.hardware.ok is True
        assert result.hardware.degraded is True
        assert result.hardware.critical_failures == ()
        entries = {entry.device_type: entry for entry in result.hardware.entries}
        assert entries["drum_controller"].is_available is True
        assert entries["lock_controller"].is_available is True
        assert entries["rfid_reader"].is_available is False
        assert entries["rfid_reader"].is_critical is False
    finally:
        container.close()


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


def _tcp_endpoint_config(*, code: str, driver_name: str, host: str, port: int) -> dict[str, object]:
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
            "transport": "tcp",
            "host": host,
            "port": port,
        },
    }
