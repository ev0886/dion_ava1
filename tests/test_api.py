from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import create_app
from app.application.time import utc_now
from app.config import AppSettings
from app.domain.enums import (
    BindingType,
    ItemStatus,
    OperationState,
    RecoveryClassification,
    RecoveryStatus,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.models import (
    InventoryBalance,
    Item,
    ManualResolutionAction,
    Operation,
    OperationSession,
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


def test_dispense_operation_accepts_null_session_id(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_null_session.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1, "session_id": None},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] is None


def test_dispense_operation_invalid_session_id_returns_404(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_invalid_session.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1, "session_id": 0},
        )

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "Operation session not found: 0"}


def test_return_operation_invalid_session_id_returns_404(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_return_invalid_session.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/return",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1, "session_id": 0},
        )

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "Operation session not found: 0"}


def test_refill_operation_invalid_session_id_returns_404(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_refill_invalid_session.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/refill",
            json={"operator_user_id": 2, "item_id": 1, "slot_id": 1, "quantity": 5, "mode": "set", "session_id": 0},
        )

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "Operation session not found: 0"}


def test_refill_operation_creates_session_when_session_id_is_null(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_refill_null_session.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/refill",
            json={"operator_user_id": 2, "item_id": 1, "slot_id": 1, "quantity": 5, "mode": "set", "session_id": None},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] is not None
    with app.state.session_factory() as session:
        assert session.get(OperationSession, response.json()["session_id"]) is not None


def test_openapi_operation_examples_do_not_suggest_invalid_session_id(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_openapi.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    dispense_example = paths["/operations/dispense"]["post"]["requestBody"]["content"]["application/json"]["examples"]["default"][
        "value"
    ]
    return_example = paths["/operations/return"]["post"]["requestBody"]["content"]["application/json"]["examples"]["default"][
        "value"
    ]
    refill_example = paths["/operations/refill"]["post"]["requestBody"]["content"]["application/json"]["examples"]["default"][
        "value"
    ]
    assert "session_id" not in dispense_example
    assert "session_id" not in return_example
    assert "session_id" not in refill_example


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


def test_manual_recovery_resolution_success_updates_case_and_persists_actions(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_manual_recovery_success.sqlite3"))
    _seed_base_domain(app)
    _seed_recovery_operation(app)

    with TestClient(app) as client:
        scan_response = client.post("/recovery/scan")
        recovery_case_id = scan_response.json()["open_cases"][0]["recovery_case_id"]

        response = client.post(
            f"/recovery/cases/{recovery_case_id}/manual-resolution",
            json={
                "operator_user_id": 1,
                "decision": "close_case",
                "comment": "Operator verified physical state",
            },
        )
        refreshed_case = client.get(f"/recovery/cases/{recovery_case_id}")

    assert response.status_code == 200
    assert response.json()["recovery_case_id"] == recovery_case_id
    assert response.json()["status"] == "resolved"
    assert response.json()["decision"] == "close_case"
    assert refreshed_case.status_code == 200
    assert refreshed_case.json()["status"] == "resolved"
    assert refreshed_case.json()["resolved_at"] is not None

    with app.state.session_factory() as session:
        recovery_case = session.get(RecoveryCase, recovery_case_id)
        recovery_actions = session.execute(select(RecoveryAction)).scalars().all()
        manual_actions = session.execute(select(ManualResolutionAction)).scalars().all()

    assert recovery_case is not None
    assert recovery_case.status is RecoveryStatus.RESOLVED
    assert recovery_case.resolved_at is not None
    assert len(recovery_actions) == 1
    assert recovery_actions[0].action_type == "manual_resolution"
    assert recovery_actions[0].comment == "Operator verified physical state"
    assert recovery_actions[0].context_json["decision"] == "close_case"
    assert len(manual_actions) == 1
    assert manual_actions[0].actor_user_id == 1
    assert manual_actions[0].action_type == "close_case"
    assert manual_actions[0].comment == "Operator verified physical state"


def test_manual_recovery_resolution_returns_404_for_missing_case(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_manual_recovery_missing.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/recovery/cases/999/manual-resolution",
            json={"operator_user_id": 1, "decision": "close_case", "comment": None},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_manual_recovery_resolution_returns_controlled_conflict_for_resolved_case(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_manual_recovery_resolved.sqlite3"))
    _seed_base_domain(app)
    recovery_case_id = _seed_resolved_recovery_case(app)

    with TestClient(app) as client:
        response = client.post(
            f"/recovery/cases/{recovery_case_id}/manual-resolution",
            json={"operator_user_id": 1, "decision": "close_case", "comment": "repeat"},
        )

    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


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
        user_role = Role(code=RoleCode.USER, name="User")
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        session.add_all((user_role, operator_role))
        session.flush()

        user = User(
            role_id=user_role.id,
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        operator = User(
            role_id=operator_role.id,
            user_code="operator-1",
            full_name="Operator One",
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
        session.add_all((user, operator, item, slot))
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


def _seed_resolved_recovery_case(app) -> int:
    with app.state.session_factory() as session:
        recovery_case = RecoveryCase(
            classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
            status=RecoveryStatus.RESOLVED,
            resolved_at=utc_now(),
            summary="Resolved recovery case",
            context_json={"operation_id": 1},
        )
        session.add(recovery_case)
        session.flush()
        session.add(
            RecoveryCaseEntity(
                recovery_case_id=recovery_case.id,
                entity_type="operation",
                entity_id="1",
                role="primary_operation",
                decision_outcome="close_case",
            )
        )
        session.commit()
        return int(recovery_case.id)
