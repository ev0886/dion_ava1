from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.domain.enums import HardwareEndpointType, StartupReadinessStatus
from app.hardware.dto import HardwareHealthEntry, HardwareHealthSnapshot, HardwareOperationStatus
from app.persistence.models import InventoryBalance, Operation, OperationStateHistory, Role, SlotItemBinding, User, UserRfidCard


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
    assert "seed-demo" in stdout
    assert stderr == ""


def test_seed_demo_seeds_expected_minimal_domain_data(tmp_path: Path) -> None:
    sqlite_filename = "cli_seed_demo.sqlite3"

    exit_code, stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            sqlite_filename,
            "--alembic-config-path",
            "alembic.ini",
            "seed-demo",
        ]
    )

    payload = json.loads(stdout)
    assert exit_code == 0
    assert "ERROR:" not in stderr
    assert payload["status"] == "ok"
    assert payload["with_recovery"] is False
    assert payload["seeded"]["inventory_quantity"] == 5
    assert payload["seeded"]["user_rfid_card_uid"] == "DEMO-USER-1"

    with _session_factory(tmp_path, sqlite_filename)() as session:
        assert len(session.execute(select(Role)).scalars().all()) == 3
        assert len(session.execute(select(User)).scalars().all()) == 3
        assert len(session.execute(select(SlotItemBinding)).scalars().all()) == 1
        assert session.execute(select(InventoryBalance)).scalar_one().quantity == 5
        assert session.execute(select(UserRfidCard)).scalar_one().card_uid == "DEMO-USER-1"
        assert session.execute(select(Operation)).scalars().all() == []


def test_seed_demo_rejects_non_empty_domain_database(tmp_path: Path) -> None:
    sqlite_filename = "cli_seed_demo_non_empty.sqlite3"
    argv = [
        "--data-dir",
        str(tmp_path),
        "--sqlite-filename",
        sqlite_filename,
        "--alembic-config-path",
        "alembic.ini",
        "seed-demo",
    ]

    first_exit_code, _first_stdout, first_stderr = _run_cli(argv)
    second_exit_code, second_stdout, second_stderr = _run_cli(argv)

    assert first_exit_code == 0
    assert "ERROR:" not in first_stderr
    assert second_exit_code == 1
    assert second_stdout == ""
    error_payload = json.loads(second_stderr[second_stderr.find("{") :])
    assert error_payload["command"] == "seed-demo"
    assert error_payload["error"] == "demo_seed_rejected"
    assert "empty domain database" in error_payload["detail"]
    assert "roles" in error_payload["detail"]


def test_seed_demo_with_recovery_creates_operation_candidate(tmp_path: Path) -> None:
    sqlite_filename = "cli_seed_demo_recovery.sqlite3"

    exit_code, stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            sqlite_filename,
            "--alembic-config-path",
            "alembic.ini",
            "seed-demo",
            "--with-recovery",
        ]
    )

    payload = json.loads(stdout)
    assert exit_code == 0
    assert "ERROR:" not in stderr
    assert payload["with_recovery"] is True
    assert payload["seeded"]["recovery_operation_id"] is not None
    assert payload["seeded"]["recovery_history_id"] is not None

    with _session_factory(tmp_path, sqlite_filename)() as session:
        operation = session.execute(select(Operation)).scalar_one()
        history = session.execute(select(OperationStateHistory)).scalar_one()
        assert operation.id == payload["seeded"]["recovery_operation_id"]
        assert history.operation_id == operation.id


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


def _session_factory(tmp_path: Path, sqlite_filename: str) -> sessionmaker:
    engine = create_engine(
        f"sqlite:///{(tmp_path / sqlite_filename).resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
