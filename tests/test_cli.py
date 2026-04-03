from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.application.dto.recovery import RecoveryResolutionResultDTO
from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.domain.enums import RecoveryStatus, StartupReadinessStatus
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


def test_apply_recovery_action_command_renders_json(monkeypatch) -> None:
    def _fake_container(_settings):
        return _FakeContainer(
            startup_result=_startup_ready(),
            recovery_result=RecoveryResolutionResultDTO(
                recovery_case_id=77,
                action_applied="confirm_operation_failed",
                case_status=RecoveryStatus.IN_PROGRESS,
                case_resolved=False,
                resolution_code=None,
                affected_operation=None,
                affected_inventory=None,
                summary_message="failure confirmed",
            ),
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(
        [
            "apply-recovery-action",
            "--recovery-case-id",
            "77",
            "--action",
            "confirm_operation_failed",
            "--actor-user-id",
            "1",
        ]
    )

    assert exit_code == 0
    assert '"recovery_case_id": 77' in stdout
    assert '"case_status": "in_progress"' in stdout
    assert stderr == ""


def test_resolve_recovery_case_command_renders_json(monkeypatch) -> None:
    def _fake_container(_settings):
        return _FakeContainer(
            startup_result=_startup_ready(),
            recovery_result=RecoveryResolutionResultDTO(
                recovery_case_id=77,
                action_applied="close_recovery_case",
                case_status=RecoveryStatus.RESOLVED,
                case_resolved=True,
                resolution_code="manual_failure_confirmed",
                affected_operation=None,
                affected_inventory=None,
                summary_message="case resolved",
            ),
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(
        [
            "resolve-recovery-case",
            "--recovery-case-id",
            "77",
            "--action",
            "close_recovery_case",
            "--resolution-code",
            "manual_failure_confirmed",
        ]
    )

    assert exit_code == 0
    assert '"case_resolved": true' in stdout
    assert '"resolution_code": "manual_failure_confirmed"' in stdout
    assert stderr == ""


@dataclass(slots=True)
class _FakeStartupService:
    result: StartupReadinessDTO

    def run_startup_checks(self) -> StartupReadinessDTO:
        return self.result


@dataclass(slots=True)
class _FakeRecoveryService:
    result: RecoveryResolutionResultDTO

    def apply_manual_action(self, request) -> RecoveryResolutionResultDTO:
        return self.result

    def resolve_case(self, request) -> RecoveryResolutionResultDTO:
        return self.result


@dataclass(slots=True)
class _FakeContainer:
    startup_result: StartupReadinessDTO
    recovery_result: RecoveryResolutionResultDTO | None = None
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(
            startup=_FakeStartupService(self.startup_result),
            recovery=_FakeRecoveryService(self.recovery_result) if self.recovery_result is not None else None,
        )

    def close(self) -> None:
        return None


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def _startup_ready() -> StartupReadinessDTO:
    return StartupReadinessDTO(
        database=DatabaseReadinessDTO(
            ok=True,
            simple_query_ok=True,
            alembic_version_table_present=True,
            message=None,
        ),
        hardware=HardwareReadinessDTO(ok=True, degraded=False, entries=(), message=None),
        recovery=RecoveryReadinessDTO(
            ok=True,
            recovery_candidates_found=False,
            recovery_candidate_count=0,
            recovery_case_count=0,
            candidate_operation_ids=(),
            message=None,
        ),
        readiness_status=StartupReadinessStatus.READY,
        message=None,
    )
