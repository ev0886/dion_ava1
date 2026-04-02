from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.api import create_app
from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.domain.enums import (
    ItemStatus,
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    RoleCode,
    SlotStatus,
    SlotType,
    StartupReadinessStatus,
    UserStatus,
)
from app.hardware.dto import HardwareOperationStatus
from app.persistence.models import AuditLog, EventLog, InventoryBalance, Item, Operation, RecoveryCase, Role, Slot, User


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


def test_execute_export_and_get_export_cli(tmp_path: Path) -> None:
    _seed_cli_export_domain(tmp_path)

    execute_exit_code, execute_stdout, execute_stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_export.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "execute-export",
            "--requested-by-user-id",
            "1",
            "--export-type",
            "operations_report",
            "--destination-path",
            "exports",
            "--operation-type",
            "dispense",
            "--operation-state",
            "completed",
        ]
    )

    assert execute_exit_code == 0
    assert '"export_type": "operations_report"' in execute_stdout
    assert "ERROR:" not in execute_stderr

    get_exit_code, get_stdout, get_stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_export.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "get-export",
            "--export-id",
            "1",
        ]
    )

    assert get_exit_code == 0
    assert '"status": "completed"' in get_stdout
    assert '"produced_file_paths"' in get_stdout
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


def _seed_cli_export_domain(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "cli_export.sqlite3"))
    with app.state.session_factory() as session:
        role = Role(code=RoleCode.ADMIN, name="Admin")
        session.add(role)
        session.flush()
        user = User(
            role_id=role.id,
            user_code="admin-1",
            full_name="Admin One",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        item = Item(
            item_group_id=None,
            sku="item-1",
            name="Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        slot = Slot(
            code="slot-1",
            slot_type=SlotType.UNIVERSAL,
            drum_position=1,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((user, item, slot))
        session.flush()
        operation = Operation(
            session_id=None,
            operation_type=OperationType.DISPENSE,
            operation_state=OperationState.COMPLETED,
            user_id=user.id,
            item_id=item.id,
            slot_id=slot.id,
            qty_requested=1,
            qty_confirmed=1,
            result="success",
            error_code=None,
            error_message=None,
            hardware_context_json={},
            business_context_json={},
            started_at=None,
            finished_at=None,
        )
        session.add(operation)
        session.flush()
        session.add(
            RecoveryCase(
                classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
                status=RecoveryStatus.OPEN,
                resolved_at=None,
                summary="seed",
                context_json=None,
            )
        )
        session.add(
            AuditLog(
                entity_type="slot",
                entity_id="1",
                action="inspect",
                actor_user_id=user.id,
                reason_code="seed",
                comment="seed",
                before_json=None,
                after_json=None,
            )
        )
        session.add(
            EventLog(
                event_type="door_opened",
                level="info",
                source="lock",
                operation_id=None,
                session_id=None,
                user_id=user.id,
                slot_id=slot.id,
                item_id=item.id,
                qty=1,
                result="ok",
                comment="seed",
                message="seed",
                payload_json=None,
            )
        )
        session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=3))
        session.commit()


def _settings(tmp_path: Path, sqlite_filename: str):
    from app.config import AppSettings

    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )
