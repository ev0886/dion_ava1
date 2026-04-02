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
from app.application.dto.logs import AuditLogEntryDTO, EventLogEntryDTO
from app.application.dto.operations import (
    OperationDTO,
    OperationDetailDTO,
    OperationInventoryTransactionDTO,
    OperationStateHistoryEntryDTO,
)
from app.application.dto.recovery import RecoveryCaseDTO, RecoveryCaseDetailDTO
from app.cli import main
from app.domain.enums import (
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    StartupReadinessStatus,
)
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


def test_query_commands_render_json_payloads(monkeypatch) -> None:
    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_query_container)

    operation_list = _run_cli(["list-operations", "--operation-type", "dispense", "--limit", "1"])
    operation_detail = _run_cli(["get-operation", "--operation-id", "10"])
    operation_history = _run_cli(["get-operation-history", "--operation-id", "10"])
    recovery_list = _run_cli(["list-recovery-cases", "--status", "open", "--limit", "1"])
    recovery_detail = _run_cli(["get-recovery-case", "--recovery-case-id", "20"])
    audit_logs = _run_cli(["list-audit-logs", "--entity-type", "operation", "--limit", "1"])
    event_logs = _run_cli(["list-event-logs", "--event-type", "operation.completed", "--limit", "1"])

    assert operation_list[0] == 0
    assert '"operation_id": 10' in operation_list[1]
    assert operation_detail[0] == 0
    assert '"recovery_case_id": 20' in operation_detail[1]
    assert operation_history[0] == 0
    assert '"state": "completed"' in operation_history[1]
    assert recovery_list[0] == 0
    assert '"recovery_case_id": 20' in recovery_list[1]
    assert recovery_detail[0] == 0
    assert '"impacted_entities"' in recovery_detail[1]
    assert audit_logs[0] == 0
    assert '"entity_type": "operation"' in audit_logs[1]
    assert event_logs[0] == 0
    assert '"event_type": "operation.completed"' in event_logs[1]


@dataclass(slots=True)
class _FakeStartupService:
    result: StartupReadinessDTO

    def run_startup_checks(self) -> StartupReadinessDTO:
        return self.result


@dataclass(slots=True)
class _FakeOperationQueryService:
    def list_operations(self, _filters):
        return (
            OperationDTO(
                operation_id=10,
                session_id=100,
                operation_type=OperationType.DISPENSE,
                operation_state=OperationState.COMPLETED,
                user_id=1,
                item_id=2,
                slot_id=3,
                qty_requested=1,
                qty_confirmed=1,
                result="completed",
                error_code=None,
                error_message=None,
                hardware_context={},
                business_context={},
                started_at=None,
                finished_at=None,
            ),
        )

    def get_operation(self, _operation_id: int) -> OperationDetailDTO:
        return OperationDetailDTO(
            operation=self.list_operations(None)[0],
            state_history=self.get_operation_history(10),
            inventory_transactions=(
                OperationInventoryTransactionDTO(
                    transaction_id=30,
                    operation_id=10,
                    session_id=100,
                    slot_id=3,
                    item_id=2,
                    transaction_type="dispense_debit",
                    quantity_delta=-1,
                    quantity_before=5,
                    quantity_after=4,
                    comment="inventory written",
                    created_at=None,
                ),
            ),
            recovery_case_id=20,
        )

    def get_operation_history(self, _operation_id: int):
        return (
            OperationStateHistoryEntryDTO(
                history_entry_id=1,
                operation_id=10,
                state=OperationState.CREATED,
                comment="created",
                context={},
                created_at=None,
            ),
            OperationStateHistoryEntryDTO(
                history_entry_id=2,
                operation_id=10,
                state=OperationState.COMPLETED,
                comment="completed",
                context={},
                created_at=None,
            ),
        )


@dataclass(slots=True)
class _FakeRecoveryQueryService:
    def list_cases(self, _filters):
        return (
            RecoveryCaseDTO(
                recovery_case_id=20,
                classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
                status=RecoveryStatus.OPEN,
                summary="Needs review",
                context={"operation_id": 10},
                created_at=None,
                resolved_at=None,
            ),
        )

    def get_case_detail(self, _recovery_case_id: int) -> RecoveryCaseDetailDTO:
        base_case = self.list_cases(None)[0]
        return RecoveryCaseDetailDTO(
            recovery_case_id=base_case.recovery_case_id or 0,
            classification=base_case.classification,
            status=base_case.status,
            summary=base_case.summary,
            context=base_case.context,
            created_at=None,
            resolved_at=None,
            impacted_entities=(),
            recovery_actions=(),
        )


@dataclass(slots=True)
class _FakeLogQueryService:
    def list_audit_logs(self, _filters):
        return (
            AuditLogEntryDTO(
                audit_log_id=40,
                entity_type="operation",
                entity_id="10",
                action="viewed",
                actor_user_id=1,
                reason_code=None,
                comment=None,
                before={},
                after={},
                created_at=None,
            ),
        )

    def list_event_logs(self, _filters):
        return (
            EventLogEntryDTO(
                event_log_id=50,
                event_type="operation.completed",
                level="info",
                source="cli-test",
                operation_id=10,
                session_id=100,
                user_id=1,
                slot_id=3,
                item_id=2,
                qty=1.0,
                result="completed",
                comment=None,
                message=None,
                payload={},
                created_at=None,
            ),
        )


@dataclass(slots=True)
class _FakeContainer:
    startup_result: StartupReadinessDTO
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(startup=_FakeStartupService(self.startup_result))

    def close(self) -> None:
        return None


def _fake_query_container(_settings):
    container = _FakeContainer(
        startup_result=StartupReadinessDTO(
            database=DatabaseReadinessDTO(True, True, True, None),
            hardware=HardwareReadinessDTO(True, False, (), None),
            recovery=RecoveryReadinessDTO(True, False, 0, 0, (), None),
            readiness_status=StartupReadinessStatus.READY,
            message=None,
        )
    )
    container.services = SimpleNamespace(
        startup=_FakeStartupService(container.startup_result),
        operations_query=_FakeOperationQueryService(),
        recovery=_FakeRecoveryQueryService(),
        logs_query=_FakeLogQueryService(),
    )
    return container


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
