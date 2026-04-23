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
from app.demo_inventory_seed import DemoInventorySeedResult, DemoSeededSlotDTO
from app.cli import main
from app.domain.enums import HardwareEndpointType, StartupReadinessStatus
from app.hardware.dto import HardwareHealthEntry, HardwareHealthSnapshot, HardwareOperationStatus


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


def test_reset_admin_password_dispatches_admin_auth_reset(monkeypatch) -> None:
    fake_container = _FakeAdminAuthContainer()
    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", lambda _settings: fake_container)

    exit_code, stdout, stderr = _run_cli(["reset-admin-password"])

    assert exit_code == 0
    assert fake_container.reset_called is True
    assert '"admin_login": "admin"' in stdout
    assert '"password_reset": true' in stdout
    assert stderr == ""


def test_seed_demo_multi_slot_inventory_runs_and_prints_seeded_slots(monkeypatch) -> None:
    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", lambda _settings: _FakeSeedContainer())
    monkeypatch.setattr("app.cli.seed_demo_multi_slot_inventory", _fake_seed_demo_multi_slot_inventory)

    exit_code, stdout, stderr = _run_cli(["seed-demo-multi-slot-inventory"])

    assert exit_code == 0
    assert '"item_id": 1' in stdout
    assert '"slot_code": "slot-p09-l05"' in stdout
    assert '"slot_codes": [' in stdout
    assert stderr == ""


def test_cli_help_lists_operator_commands() -> None:
    exit_code, stdout, stderr = _run_cli(["--help"])

    assert exit_code == 0
    assert "startup-check" in stdout
    assert "hardware-health" in stdout
    assert "recovery-scan" in stdout
    assert "reset-admin-password" in stdout
    assert "seed-demo-multi-slot-inventory" in stdout
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
class _FakeAdminAuthService:
    container: "_FakeAdminAuthContainer"

    def reset_to_default_password(self) -> None:
        self.container.reset_called = True


@dataclass(slots=True)
class _FakeAdminAuthContainer:
    services: SimpleNamespace | None = None
    reset_called: bool = False

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(admin_auth=_FakeAdminAuthService(self))

    def close(self) -> None:
        return None


@dataclass(slots=True)
class _FakeSeedContainer:
    session: object | None = None

    def __post_init__(self) -> None:
        self.session = object()

    def close(self) -> None:
        return None


def _fake_seed_demo_multi_slot_inventory(_session, *, item_id: int) -> DemoInventorySeedResult:
    return DemoInventorySeedResult(
        item_id=item_id,
        slot_codes=("slot-p09-l05",),
        seeded_slots=(
            DemoSeededSlotDTO(
                slot_id=140,
                slot_code="slot-p09-l05",
                drum_position=9,
                board_address=0,
                lock_number=5,
                quantity=1,
            ),
        ),
    )


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            exit_code = main(argv)
        except SystemExit as error:
            exit_code = int(error.code)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
