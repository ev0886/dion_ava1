from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.application.composition import create_bootstrapped_application_container
from app.cli import main
from app.config import AppSettings, HardwareProvider
from app.domain.enums import StartupReadinessStatus


def test_startup_readiness_smoke_with_mock_provider(tmp_path: Path) -> None:
    container = create_bootstrapped_application_container(_mock_settings(tmp_path, "smoke_mock.sqlite3"))
    try:
        result = container.services.startup.run_startup_checks()

        assert container.hardware.provider is HardwareProvider.MOCK
        assert result.readiness_status is StartupReadinessStatus.READY
        assert result.hardware.degraded is False
    finally:
        container.close()


def test_startup_readiness_smoke_with_real_provider_and_fake_transports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    monkeypatch.setattr(hardware_factory, "_create_transport_client", _fake_transport_client)

    container = create_bootstrapped_application_container(_real_settings(tmp_path, "smoke_real.sqlite3"))
    try:
        result = container.services.startup.run_startup_checks()

        assert container.hardware.provider is HardwareProvider.REAL
        assert result.readiness_status is StartupReadinessStatus.READY
        assert all(entry.is_available is True for entry in result.hardware.entries)
    finally:
        container.close()


def test_api_readiness_smoke_with_composed_real_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    monkeypatch.setattr(hardware_factory, "_create_transport_client", _fake_transport_client)
    app = create_app(_real_settings(tmp_path, "smoke_api_real.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json()["readiness_status"] == "ready"


def test_cli_hardware_health_smoke_with_composed_real_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import cli as cli_module
    from app.hardware import factory as hardware_factory

    monkeypatch.setattr(hardware_factory, "_create_transport_client", _fake_transport_client)
    settings = _real_settings(tmp_path, "smoke_cli_real.sqlite3")
    monkeypatch.setattr(
        cli_module,
        "create_bootstrapped_application_container",
        lambda _settings: create_bootstrapped_application_container(settings),
    )

    exit_code, stdout, stderr = _run_cli(["hardware-health"])

    assert exit_code == 0
    assert '"provider": "real"' in stdout
    assert '"safe_boundary_check": true' in stdout
    assert '"real_endpoint_config"' in stdout
    assert '"drum"' in stdout
    assert '"lock"' in stdout
    assert '"rfid"' in stdout
    assert '"is_available": true' in stdout
    assert "ERROR:" not in stderr


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


class _FakeTransport:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        if not self._responses:
            raise AssertionError("No fake transport responses remain.")
        return self._responses.pop(0)

    def send(self, payload: bytes) -> None:
        return None


def _fake_transport_client(config):
    if config is None:
        return None
    if config.endpoint.code == "rfid-1":
        return _FakeTransport([b"PONG\n"])
    if config.endpoint.code == "lock-1":
        return _FakeTransport([bytes.fromhex("02 00 00 8F 10 00 03 A4")])
    return _FakeTransport([bytes.fromhex("24 00 00 C1")])


def _mock_settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.MOCK,
    )


def _real_settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM2"),
        },
    )


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
