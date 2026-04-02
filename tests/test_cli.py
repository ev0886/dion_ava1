from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.application.composition import create_bootstrapped_application_container
from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.config import AppSettings
from app.domain.enums import StartupReadinessStatus
from app.domain.enums import RoleCode, UserStatus
from app.hardware.dto import HardwareOperationStatus
from app.persistence.models import Role, User


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


def test_get_system_config_prints_effective_config(tmp_path: Path) -> None:
    exit_code, stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_system_config.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "get-system-config",
        ]
    )

    assert exit_code == 0
    assert '"hardware"' in stdout
    assert '"writable_fields"' in stdout
    assert "ERROR:" not in stderr


def test_update_system_config_updates_persisted_effective_settings(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="cli_update_system_config.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )
    _seed_cli_operator(settings)

    update_exit_code, update_stdout, update_stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_update_system_config.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "update-system-config",
            "--actor-user-id",
            "1",
            "--patch-json",
            '{"hardware_provider":"real","export_default_destination_path":"var/cli-exports"}',
        ]
    )
    get_exit_code, get_stdout, get_stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_update_system_config.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "get-system-config",
        ]
    )

    assert update_exit_code == 0
    assert '"value": "real"' in update_stdout
    assert "ERROR:" not in update_stderr
    assert get_exit_code == 0
    assert '"value": "real"' in get_stdout
    assert '"value": "var/cli-exports"' in get_stdout
    assert "ERROR:" not in get_stderr


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


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def _seed_cli_operator(settings: AppSettings) -> None:
    container = create_bootstrapped_application_container(settings)
    try:
        role = Role(code=RoleCode.OPERATOR, name="Operator")
        container.session.add(role)
        container.session.flush()
        container.session.add(
            User(
                role_id=role.id,
                user_code="operator-1",
                full_name="Operator One",
                status=UserStatus.ACTIVE,
                is_active=True,
            )
        )
        container.session.commit()
    finally:
        container.close()
