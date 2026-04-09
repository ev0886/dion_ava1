from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.domain.enums import HardwareEndpointType, StartupReadinessStatus
from app.hardware import RealRfidAdapter
from app.hardware.dto import HardwareHealthEntry, HardwareHealthSnapshot, HardwareOperationStatus
from app.hardware.rfid_rusguard import RusGuardAcmStatusTransport
from app.hardware.transport_config import RfidHardwareEndpointTransportConfig


def test_startup_check_returns_success_for_healthy_temp_environment(tmp_path: Path) -> None:
    exit_code, stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_healthy.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "startup-check",
        ]
    )

    assert exit_code == 0
    assert '"readiness_status": "ready"' in stdout
    assert "ERROR:" not in stderr


def test_startup_check_returns_non_zero_when_startup_is_not_ready(monkeypatch) -> None:
    def _fake_container(_settings):
        return _FakeContainer(
            startup_result=StartupReadinessDTO(
                database=DatabaseReadinessDTO(
                    ok=False,
                    simple_query_ok=False,
                    alembic_version_table_present=False,
                    message="db failed",
                ),
                hardware=HardwareReadinessDTO(ok=False, degraded=False, entries=(), message=None),
                recovery=RecoveryReadinessDTO(
                    ok=False,
                    recovery_candidates_found=False,
                    recovery_candidate_count=0,
                    recovery_case_count=0,
                    candidate_operation_ids=(),
                    message=None,
                ),
                readiness_status=StartupReadinessStatus.NOT_READY,
                message="db failed",
            )
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(["startup-check"])

    assert exit_code == 1
    assert '"readiness_status": "not_ready"' in stdout
    assert stderr == ""


def test_hardware_health_prints_three_mock_device_statuses(tmp_path: Path) -> None:
    exit_code, stdout, _stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_hardware.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "hardware-health",
        ]
    )

    assert exit_code == 0
    assert '"drum"' in stdout
    assert '"lock"' in stdout
    assert '"rfid"' in stdout


def test_hardware_health_returns_non_zero_when_any_device_is_unavailable(monkeypatch) -> None:
    def _fake_container(_settings):
        return _FakeHardwareContainer(all_ok=False)

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(["hardware-health"])

    assert exit_code == 1
    assert '"all_ok"' not in stdout
    assert '"status": "failure"' in stdout
    assert stderr == ""


def test_recovery_scan_runs_and_prints_deterministic_summary(tmp_path: Path) -> None:
    exit_code, stdout, _stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_recovery.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "recovery-scan",
        ]
    )

    assert exit_code == 0
    assert '"candidate_operation_ids": []' in stdout
    assert '"open_case_count": 0' in stdout
    assert '"unfinished_operation_ids": []' in stdout


def test_cli_help_lists_operator_commands() -> None:
    exit_code, stdout, stderr = _run_cli(["--help"])

    assert exit_code == 0
    assert "startup-check" in stdout
    assert "hardware-health" in stdout
    assert "recovery-scan" in stdout
    assert stderr == ""


def test_rfid_rg_get_card_runs_narrow_diagnostic_command(monkeypatch) -> None:
    adapter = RealRfidAdapter(
        config=_rfid_config(),
        transport=RusGuardAcmStatusTransport(
            settings=_rfid_config().transport,
            timeouts=_rfid_config().endpoint.timeouts,
            sdk_loader=lambda _override: _FakeCliRusGuardSdk(),
        ),
    )

    def _fake_container(_settings):
        return _FakeRfidDiagnosticContainer(adapter)

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(["rfid-rg-get-card"])

    assert exit_code == 0
    assert '"status_type": 9' in stdout
    assert '"uid": "A1B2C3D4"' in stdout
    assert '"uid_size": 4' in stdout
    assert stderr == ""


@dataclass(slots=True)
class _FakeStartupService:
    result: StartupReadinessDTO

    def run_startup_checks(self) -> StartupReadinessDTO:
        return self.result


@dataclass(slots=True)
class _FakeContainer:
    startup_result: StartupReadinessDTO
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(startup=_FakeStartupService(self.startup_result))

    def close(self) -> None:
        return None


@dataclass(slots=True)
class _FakeHardwareFacade:
    all_ok: bool

    def hardware_healthcheck(self) -> HardwareHealthSnapshot:
        status = HardwareOperationStatus.SUCCESS if self.all_ok else HardwareOperationStatus.FAILURE
        message = None if self.all_ok else "offline"
        return HardwareHealthSnapshot(
            drum=HardwareHealthEntry(
                device_type=HardwareEndpointType.DRUM_CONTROLLER,
                is_available=self.all_ok,
                status=status,
                message=message,
            ),
            lock=HardwareHealthEntry(
                device_type=HardwareEndpointType.LOCK_CONTROLLER,
                is_available=self.all_ok,
                status=status,
                message=message,
            ),
            rfid=HardwareHealthEntry(
                device_type=HardwareEndpointType.RFID_READER,
                is_available=self.all_ok,
                status=status,
                message=message,
            ),
        )


@dataclass(slots=True)
class _FakeHardwareContainer:
    all_ok: bool
    hardware: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.hardware = SimpleNamespace(facade=_FakeHardwareFacade(self.all_ok))

    def close(self) -> None:
        return None


@dataclass(slots=True)
class _FakeRfidDiagnosticContainer:
    adapter: RealRfidAdapter
    hardware: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.hardware = SimpleNamespace(rfid_reader=self.adapter)

    def close(self) -> None:
        return None


class _FakeCliRusGuardSdk:
    def RG_InitializeLib(self) -> int:
        return 0

    def RG_FindEndPoints(self, handle_ptr, _endpoint_type_mask: int, count_ptr) -> int:
        handle_ptr._obj.value = 1234
        count_ptr._obj.value = 1
        return 0

    def RG_GetFoundEndPointInfo(self, _handle, _index: int, endpoint_info_ptr) -> int:
        endpoint_info = endpoint_info_ptr._obj
        endpoint_info.type = 2
        endpoint_info.address = b"/dev/ttyACM0"
        endpoint_info.friendly_name = b"RusGuard ACM"
        return 0

    def RG_InitDevice(self, _endpoint_ptr, _address: int) -> int:
        return 0

    def RG_GetCard(self, _endpoint_ptr, _address: int, status_type_ptr, uid_buffer, _uid_buffer_size: int, uid_size_ptr) -> int:
        status_type_ptr._obj.value = 9
        uid_size_ptr._obj.value = 4
        uid_buffer[0] = 0xA1
        uid_buffer[1] = 0xB2
        uid_buffer[2] = 0xC3
        uid_buffer[3] = 0xD4
        return 0

    def RG_CloseDevice(self, _endpoint_ptr, _address: int) -> int:
        return 0

    def RG_CloseResource(self, _handle) -> int:
        return 0

    def RG_Uninitialize(self) -> int:
        return 0


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            exit_code = main(argv)
        except SystemExit as error:
            exit_code = int(error.code)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def _rfid_config() -> RfidHardwareEndpointTransportConfig:
    return RfidHardwareEndpointTransportConfig.model_validate(
        {
            "endpoint": {
                "code": "rfid-1",
                "driver_name": "rfid-driver",
                "enabled": True,
                "timeouts": {
                    "connect_timeout_ms": 1000,
                    "read_timeout_ms": 1000,
                    "write_timeout_ms": 1000,
                },
            },
            "transport": {
                "transport": "serial",
                "port": "/dev/ttyACM0",
            },
        }
    )
