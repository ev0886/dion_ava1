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
from app.hardware.dto import HardwareHealthEntry, HardwareHealthSnapshot, HardwareOperationStatus
from app.hardware.rfid_debug import RfidDebugChunk, RfidSerialExchangeCapture


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
    assert "rfid-debug-exchange" in stdout
    assert stderr == ""


def test_rfid_debug_exchange_prints_capture_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.cli._resolve_rfid_debug_config",
        lambda settings: SimpleNamespace(
            transport=SimpleNamespace(port="/dev/ttyACM0", baudrate=9600, data_bits=8, parity="none", stop_bits=1),
            endpoint=SimpleNamespace(
                timeouts=SimpleNamespace(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000)
            ),
        ),
    )
    monkeypatch.setattr(
        "app.cli.capture_rfid_serial_exchange",
        lambda **kwargs: RfidSerialExchangeCapture(
            port="/dev/ttyACM0",
            request_ascii="READ\n",
            request_hex="524541440A",
            max_chunks=4,
            chunk_count=2,
            combined_hex="524541440A5549443A3031323334350A",
            combined_ascii="READ\nUID:012345\n",
            combined_lines=("READ", "UID:012345"),
            chunks=(
                RfidDebugChunk(index=0, bytes_hex="524541440A", bytes_ascii="READ\n", lines=("READ",)),
                RfidDebugChunk(index=1, bytes_hex="5549443A3031323334350A", bytes_ascii="UID:012345\n", lines=("UID:012345",)),
            ),
        ),
    )

    exit_code, stdout, stderr = _run_cli(["rfid-debug-exchange"])

    assert exit_code == 0
    assert '"combined_lines": [' in stdout
    assert '"READ"' in stdout
    assert '"UID:012345"' in stdout
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


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            exit_code = main(argv)
        except SystemExit as error:
            exit_code = int(error.code)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
