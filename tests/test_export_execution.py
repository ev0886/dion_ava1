from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.application.export_service import build_export_execution_request
from app.config import AppSettings
from app.domain.enums import (
    ExportStatus,
    ItemStatus,
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.models import AuditLog, EventLog, Export, InventoryBalance, Item, Operation, RecoveryCase, Role, Slot, User


def test_operations_export_execution_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "operations_export.sqlite3"))
    _seed_reporting_domain(app)

    with app.state.session_factory() as session:
        export_service = _build_export_service(app, session)
        result = export_service.execute_export(
            build_export_execution_request(
                requested_by_user_id=1,
                export_type="operations_report",
                destination_type="filesystem",
                destination_path="exports",
                operation_type=OperationType.DISPENSE,
                operation_state=OperationState.COMPLETED,
                created_from=datetime(2026, 1, 1, 0, 0, 0),
                created_to=datetime(2026, 1, 1, 23, 59, 59),
            )
        )
        export_row = session.get(Export, result.export_id)

    assert result.status is ExportStatus.COMPLETED
    assert result.row_count == 1
    assert result.destination_path.exists()
    assert [path.name for path in result.produced_file_paths] == [
        "operations_report.json",
        "operations_report.csv",
        "manifest.json",
    ]
    assert export_row is not None
    assert export_row.status is ExportStatus.COMPLETED
    assert export_row.file_path is not None


def test_recovery_audit_event_and_inventory_exports_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "multi_export.sqlite3"))
    _seed_reporting_domain(app)

    with app.state.session_factory() as session:
        export_service = _build_export_service(app, session)
        recovery = export_service.execute_export(
            build_export_execution_request(
                requested_by_user_id=1,
                export_type="recovery_cases_report",
                destination_type="filesystem",
                destination_path="exports",
                recovery_status=RecoveryStatus.OPEN,
                recovery_classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
            )
        )
        audit = export_service.execute_export(
            build_export_execution_request(
                requested_by_user_id=1,
                export_type="audit_logs_report",
                destination_type="filesystem",
                destination_path="exports",
                entity_type="slot",
                actor_user_id=1,
            )
        )
        event = export_service.execute_export(
            build_export_execution_request(
                requested_by_user_id=1,
                export_type="event_logs_report",
                destination_type="filesystem",
                destination_path="exports",
                event_type="door_opened",
                level="info",
                slot_id=1,
                item_id=1,
                user_id=1,
            )
        )
        inventory = export_service.execute_export(
            build_export_execution_request(
                requested_by_user_id=1,
                export_type="inventory_balances_snapshot_report",
                destination_type="filesystem",
                destination_path="exports",
                slot_id=1,
                item_id=1,
            )
        )

    assert recovery.row_count == 1
    assert audit.row_count == 1
    assert event.row_count == 1
    assert inventory.row_count == 1
    assert recovery.produced_file_paths[0].read_text(encoding="utf-8").startswith("{")


def test_invalid_export_type_rejected(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "invalid_type.sqlite3"))
    _seed_reporting_domain(app)

    with app.state.session_factory() as session:
        export_service = _build_export_service(app, session)
        try:
            export_service.execute_export(
                build_export_execution_request(
                    requested_by_user_id=1,
                    export_type="unsupported_report",
                    destination_type="filesystem",
                    destination_path="exports",
                )
            )
        except Exception as error:
            assert str(error) == "Unsupported export_type: unsupported_report"
        else:
            raise AssertionError("Expected unsupported export type to fail")


def test_invalid_destination_rejected(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "invalid_destination.sqlite3"))
    _seed_reporting_domain(app)

    with app.state.session_factory() as session:
        export_service = _build_export_service(app, session)
        try:
            export_service.execute_export(
                build_export_execution_request(
                    requested_by_user_id=1,
                    export_type="operations_report",
                    destination_type="s3",
                    destination_path="exports",
                )
            )
        except Exception as error:
            assert str(error) == "Only filesystem destination_type is supported"
        else:
            raise AssertionError("Expected invalid destination to fail")


def test_export_get_endpoint_returns_metadata_and_artifacts(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_exports.sqlite3"))
    _seed_reporting_domain(app)

    with TestClient(app) as client:
        execute_response = client.post(
            "/exports/execute",
            json={
                "requested_by_user_id": 1,
                "export_type": "operations_report",
                "destination_type": "filesystem",
                "destination_path": "exports",
                "operation_type": "dispense",
                "operation_state": "completed",
            },
        )

        assert execute_response.status_code == 200
        export_id = execute_response.json()["export_id"]

        get_response = client.get(f"/exports/{export_id}")

    assert get_response.status_code == 200
    assert get_response.json()["status"] == "completed"
    assert len(get_response.json()["produced_file_paths"]) == 3


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _build_export_service(app, session):
    from app.application.composition import build_application_container

    container = build_application_container(
        settings=app.state.settings,
        engine=app.state.engine,
        session_factory=app.state.session_factory,
        session=session,
    )
    return container.services.exports


def _seed_reporting_domain(app) -> None:
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

        started_at = datetime(2026, 1, 1, 12, 0, 0)
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
            hardware_context_json={"position": 1},
            business_context_json={"kind": "seed"},
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=1),
        )
        session.add(operation)
        session.flush()
        session.add(
            RecoveryCase(
                classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
                status=RecoveryStatus.OPEN,
                summary="Needs manual review",
                resolved_at=None,
            )
        )
        session.add(
            AuditLog(
                entity_type="slot",
                entity_id="1",
                action="inspect",
                actor_user_id=user.id,
                reason_code="manual_check",
                comment="seed audit log",
                before_json={"state": "locked"},
                after_json={"state": "open"},
            )
        )
        session.add(
            EventLog(
                event_type="door_opened",
                level="info",
                source="lock_controller",
                operation_id=operation.id,
                session_id=None,
                user_id=user.id,
                slot_id=slot.id,
                item_id=item.id,
                qty=1,
                result="ok",
                comment="seed event log",
                message="door opened",
                payload_json={"lock": 1},
            )
        )
        session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=7))
        session.commit()

        exports_dir = app.state.settings.data_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        metadata = {"seeded": True}
        (exports_dir / "seed.json").write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
