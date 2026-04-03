from __future__ import annotations

from pathlib import Path

from app.application import create_bootstrapped_application_container
from app.application.time import utc_now
from app.config import AppSettings, HardwareProvider
from app.domain.enums import ExportStatus, OperationState, OperationType, RecoveryClassification, RecoveryStatus
from app.persistence.models import AuditLog, EventLog, Export, Operation, RecoveryCase


def test_diagnostics_summary_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "diagnostics_summary.sqlite3")

    try:
        summary = container.services.diagnostics.get_summary()
    finally:
        container.close()

    assert summary.readiness_status.value == "ready"
    assert summary.hardware_issues == ()
    assert summary.recent_failed_operations == ()
    assert summary.recent_recovery_activity == ()
    assert summary.recent_denials == ()
    assert summary.recent_export_failures == ()


def test_troubleshooting_snapshot_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "troubleshooting_snapshot.sqlite3")
    _seed_logs(container)
    _seed_failed_export(container)

    try:
        snapshot = container.services.diagnostics.get_troubleshooting_snapshot()
    finally:
        container.close()

    assert snapshot.readiness.readiness_status.value == "ready"
    assert len(snapshot.hardware_snapshot.entries) == 3
    assert snapshot.recent_event_signals[0].event_type == "service_mode_entered"
    assert snapshot.recent_audit_signals[0].action == "service_mode_enter"
    assert snapshot.recent_export_failures[0].status is ExportStatus.FAILED


def test_degraded_hardware_reflected_in_diagnostics_summary(tmp_path: Path) -> None:
    container = _container(
        tmp_path,
        "diagnostics_degraded.sqlite3",
        hardware_provider=HardwareProvider.STUB_REAL,
    )

    try:
        summary = container.services.diagnostics.get_summary()
    finally:
        container.close()

    assert summary.readiness_status.value == "degraded"
    assert len(summary.hardware_issues) == 3
    assert {issue.device_type for issue in summary.hardware_issues} == {
        "drum_controller",
        "lock_controller",
        "rfid_reader",
    }


def test_recent_failed_operation_visibility(tmp_path: Path) -> None:
    container = _container(tmp_path, "diagnostics_failed_operation.sqlite3")
    _seed_failed_operation(container)

    try:
        summary = container.services.diagnostics.get_summary()
    finally:
        container.close()

    assert len(summary.recent_failed_operations) == 1
    assert summary.recent_failed_operations[0].operation_state == "failed"
    assert summary.recent_failed_operations[0].error_code == "hardware_timeout"


def test_recent_recovery_visibility(tmp_path: Path) -> None:
    container = _container(tmp_path, "diagnostics_recovery.sqlite3")
    _seed_recovery_case(container)

    try:
        summary = container.services.diagnostics.get_summary()
    finally:
        container.close()

    assert len(summary.recent_recovery_activity) == 1
    assert summary.recent_recovery_activity[0].classification == "manual_review_required"
    assert "Manual review" in summary.recent_recovery_activity[0].summary


def _container(
    tmp_path: Path,
    sqlite_filename: str,
    *,
    hardware_provider: HardwareProvider = HardwareProvider.MOCK,
):
    return create_bootstrapped_application_container(
        AppSettings(
            data_dir=tmp_path,
            sqlite_filename=sqlite_filename,
            alembic_config_path=Path("alembic.ini"),
            hardware_provider=hardware_provider,
        )
    )


def _seed_failed_operation(container) -> None:
    session = container.session
    session.add(
        Operation(
            session_id=None,
            operation_type=OperationType.DISPENSE,
            operation_state=OperationState.FAILED,
            user_id=None,
            item_id=None,
            slot_id=None,
            qty_requested=1,
            qty_confirmed=None,
            result="hardware_error",
            error_code="hardware_timeout",
            error_message="Drum did not respond in time",
            hardware_context_json={},
            business_context_json={},
            started_at=utc_now(),
            finished_at=utc_now(),
        )
    )
    session.commit()


def _seed_recovery_case(container) -> None:
    session = container.session
    session.add(
        RecoveryCase(
            classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
            status=RecoveryStatus.OPEN,
            resolved_at=None,
            summary="Manual review required for interrupted dispense",
            context_json={"operation_id": 7},
        )
    )
    session.commit()


def _seed_logs(container) -> None:
    session = container.session
    session.add(
        EventLog(
            event_type="service_mode_entered",
            level="info",
            source="service_mode_service",
            operation_id=None,
            session_id=None,
            user_id=None,
            slot_id=None,
            item_id=None,
            qty=None,
            result="active",
            comment="Service mode opened",
            message="Service mode opened",
            payload_json={"entered_via": "test"},
        )
    )
    session.add(
        AuditLog(
            entity_type="operation_session",
            entity_id="1",
            action="service_mode_enter",
            actor_user_id=None,
            reason_code=None,
            comment="Service mode opened",
            before_json=None,
            after_json=None,
        )
    )
    session.commit()


def _seed_failed_export(container) -> None:
    session = container.session
    session.add(
        Export(
            requested_by_user_id=None,
            export_type="service_diagnostics_bundle",
            destination_type="filesystem",
            destination_path="var/exports",
            status=ExportStatus.FAILED,
            completed_at=utc_now(),
            file_path=None,
            error_message="Export destination unavailable",
            comment="seeded failure",
        )
    )
    session.commit()
