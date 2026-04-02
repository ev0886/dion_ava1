from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import AppSettings
from app.domain.enums import (
    BindingType,
    ItemStatus,
    OperationState,
    RecoveryActionStatus,
    RecoveryClassification,
    RecoveryStatus,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.models import (
    AuditLog,
    EventLog,
    InventoryBalance,
    Item,
    Operation,
    OperationStateHistory,
    RecoveryAction,
    RecoveryCase,
    RecoveryCaseEntity,
    Role,
    Slot,
    SlotItemBinding,
    User,
)


def test_app_creation_smoke(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_smoke.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_and_readiness(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_readiness.sqlite3"))

    with TestClient(app) as client:
        health = client.get("/health")
        readiness = client.get("/readiness")

    assert health.status_code == 200
    assert readiness.status_code == 200
    assert readiness.json()["readiness_status"] == "ready"


def test_auth_and_inventory_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_inventory.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        auth_response = client.post("/auth/resolve", json={"user_id": 1})
        inventory_response = client.get("/inventory/1/1")

    assert auth_response.status_code == 200
    assert auth_response.json()["user_code"] == "user-1"
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 5


def test_dispense_operation_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["qty_confirmed"] == 1


def test_recovery_endpoints_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_recovery.sqlite3"))
    _seed_base_domain(app)
    _seed_recovery_operation(app)

    with TestClient(app) as client:
        scan_response = client.post("/recovery/scan")

        assert scan_response.status_code == 200
        payload = scan_response.json()
        assert payload["candidate_operation_ids"] == [1]

        recovery_case_id = payload["open_cases"][0]["recovery_case_id"]
        case_response = client.get(f"/recovery/cases/{recovery_case_id}")
        manual_response = client.get(f"/recovery/cases/{recovery_case_id}/manual-resolution")

    assert case_response.status_code == 200
    assert manual_response.status_code == 200
    assert manual_response.json()["recovery_case_id"] == recovery_case_id


def test_query_and_feed_endpoints_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_query.sqlite3"))
    _seed_base_domain(app)
    ids = _seed_query_read_models(app)

    with TestClient(app) as client:
        operations = client.get("/operations", params={"operation_type": "dispense", "user_id": 1, "limit": 5})
        operation_detail = client.get(f"/operations/{ids['operation_id']}")
        operation_history = client.get(f"/operations/{ids['operation_id']}/history")
        recovery_cases = client.get(
            "/recovery/cases",
            params={"status": "open", "classification": "manual_review_required"},
        )
        recovery_case = client.get(f"/recovery/cases/{ids['recovery_case_id']}")
        audit_logs = client.get("/audit-logs", params={"entity_type": "operation", "actor_user_id": 1})
        event_logs = client.get("/event-logs", params={"event_type": "operation.completed", "level": "info"})

    assert operations.status_code == 200
    assert operations.json()[0]["operation_id"] == ids["operation_id"]
    assert operation_detail.status_code == 200
    assert operation_detail.json()["recovery_case_id"] == ids["recovery_case_id"]
    assert operation_history.status_code == 200
    assert operation_history.json()[-1]["state"] == "completed"
    assert recovery_cases.status_code == 200
    assert recovery_cases.json()[0]["recovery_case_id"] == ids["recovery_case_id"]
    assert recovery_case.status_code == 200
    assert recovery_case.json()["impacted_entities"][0]["entity_type"] == "operation"
    assert audit_logs.status_code == 200
    assert audit_logs.json()[0]["entity_type"] == "operation"
    assert event_logs.status_code == 200
    assert event_logs.json()[0]["event_type"] == "operation.completed"


def test_error_mapping_returns_400_for_validation_error(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_errors.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/inventory/0/1")

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _seed_base_domain(app) -> None:
    with app.state.session_factory() as session:
        role = Role(code=RoleCode.USER, name="User")
        session.add(role)
        session.flush()

        user = User(
            role_id=role.id,
            user_code="user-1",
            full_name="User One",
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
            drum_position=3,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((user, item, slot))
        session.flush()
        session.add(
            SlotItemBinding(
                slot_id=slot.id,
                item_id=item.id,
                binding_type=BindingType.RETURN,
                is_active=True,
                valid_from=None,
                valid_to=None,
            )
        )
        session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=5))
        session.commit()


def _seed_recovery_operation(app) -> None:
    with app.state.session_factory() as session:
        operation = Operation(
            session_id=None,
            operation_type="dispense",
            operation_state=OperationState.USER_ACTION_PENDING,
            user_id=1,
            item_id=1,
            slot_id=1,
            qty_requested=1,
            qty_confirmed=None,
            result=None,
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
            OperationStateHistory(
                operation_id=operation.id,
                state=OperationState.USER_ACTION_PENDING,
                comment="seeded recovery candidate",
                context_json={},
            )
        )
        session.commit()


def _seed_query_read_models(app) -> dict[str, int]:
    with app.state.session_factory() as session:
        operation = Operation(
            session_id=None,
            operation_type="dispense",
            operation_state=OperationState.COMPLETED,
            user_id=1,
            item_id=1,
            slot_id=1,
            qty_requested=1,
            qty_confirmed=1,
            result="completed",
            error_code=None,
            error_message=None,
            hardware_context_json={"lock_number": 1},
            business_context_json={"source": "api_test"},
            started_at=None,
            finished_at=None,
        )
        session.add(operation)
        session.flush()
        session.add_all(
            (
                OperationStateHistory(
                    operation_id=operation.id,
                    state=OperationState.CREATED,
                    comment="created",
                    context_json={},
                ),
                OperationStateHistory(
                    operation_id=operation.id,
                    state=OperationState.COMPLETED,
                    comment="completed",
                    context_json={},
                ),
            )
        )
        recovery_case = RecoveryCase(
            classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
            status=RecoveryStatus.OPEN,
            resolved_at=None,
            summary="Operation requires review",
            context_json={"operation_id": operation.id},
        )
        session.add(recovery_case)
        session.flush()
        session.add_all(
            (
                RecoveryCaseEntity(
                    recovery_case_id=recovery_case.id,
                    entity_type="operation",
                    entity_id=str(operation.id),
                    role="primary_operation",
                    decision_outcome=None,
                ),
                RecoveryAction(
                    recovery_case_id=recovery_case.id,
                    action_type="manual_review",
                    status=RecoveryActionStatus.PLANNED,
                    applied_at=None,
                    comment="Review operation",
                    context_json={},
                ),
                AuditLog(
                    entity_type="operation",
                    entity_id=str(operation.id),
                    action="viewed",
                    actor_user_id=1,
                    reason_code="api_test",
                    comment="Audit feed seed",
                    before_json={},
                    after_json={"state": "completed"},
                ),
                EventLog(
                    event_type="operation.completed",
                    level="info",
                    source="api-test",
                    operation_id=operation.id,
                    session_id=operation.session_id,
                    user_id=1,
                    slot_id=1,
                    item_id=1,
                    qty=1,
                    result="completed",
                    comment="Event feed seed",
                    message="Completed",
                    payload_json={"operation_id": operation.id},
                ),
            )
        )
        session.commit()
        return {"operation_id": operation.id, "recovery_case_id": recovery_case.id}
