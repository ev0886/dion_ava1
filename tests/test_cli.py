from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.application.dto.service_mode import DiagnosticHardwareEntryDTO, DiagnosticSnapshotDTO
from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.domain.enums import StartupReadinessStatus
from app.hardware.dto import HardwareOperationStatus


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
                hardware=HardwareReadinessDTO(
                    provider_mode="real",
                    ok=False,
                    degraded=False,
                    entries=(),
                    critical_failures=("drum_controller",),
                    message=None,
                ),
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


def test_hardware_diagnostics_prints_provider_and_entries(monkeypatch) -> None:
    def _fake_container(_settings):
        return _FakeContainer(
            startup_result=_healthy_startup_result(),
            diagnostic_snapshot=DiagnosticSnapshotDTO(
                session_id=None,
                captured_at=None,  # type: ignore[arg-type]
                provider_mode="real",
                overall_ok=False,
                overall_status="degraded",
                entries=(
                    DiagnosticHardwareEntryDTO(
                        provider_mode="real",
                        device_type="drum_controller",
                        ok=False,
                        is_available=False,
                        is_critical=True,
                        status=HardwareOperationStatus.UNAVAILABLE,
                        summary="Drum controller transport request failed.",
                        detail={"operation": "ping"},
                    ),
                ),
            ),
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(["hardware-diagnostics"])

    assert exit_code == 0
    assert '"provider_mode": "real"' in stdout
    assert '"overall_status": "degraded"' in stdout
    assert '"device_type": "drum_controller"' in stdout
    assert stderr == ""


@dataclass(slots=True)
class _FakeStartupService:
    result: StartupReadinessDTO

    def run_startup_checks(self) -> StartupReadinessDTO:
        return self.result


@dataclass(slots=True)
class _FakeServiceModeService:
    snapshot: DiagnosticSnapshotDTO

    def get_hardware_snapshot(self, *, session_id: int | None = None) -> DiagnosticSnapshotDTO:
        return self.snapshot


@dataclass(slots=True)
class _FakeContainer:
    startup_result: StartupReadinessDTO
    diagnostic_snapshot: DiagnosticSnapshotDTO | None = None
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(
            startup=_FakeStartupService(self.startup_result),
            service_mode=_FakeServiceModeService(self.diagnostic_snapshot or _healthy_snapshot()),
        )

    def close(self) -> None:
        return None


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def _healthy_startup_result() -> StartupReadinessDTO:
    return StartupReadinessDTO(
        database=DatabaseReadinessDTO(
            ok=True,
            simple_query_ok=True,
            alembic_version_table_present=True,
            message=None,
        ),
        hardware=HardwareReadinessDTO(
            provider_mode="mock",
            ok=True,
            degraded=False,
            entries=(),
            critical_failures=(),
            message=None,
        ),
        recovery=RecoveryReadinessDTO(
            ok=True,
            recovery_candidates_found=False,
            recovery_candidate_count=0,
            recovery_case_count=0,
            candidate_operation_ids=(),
            message=None,
        ),
        readiness_status=StartupReadinessStatus.READY,
        message="Startup checks passed.",
    )


def _healthy_snapshot() -> DiagnosticSnapshotDTO:
    return DiagnosticSnapshotDTO(
        session_id=None,
        captured_at=None,  # type: ignore[arg-type]
        provider_mode="mock",
        overall_ok=True,
        overall_status="ready",
        entries=(),
    )
