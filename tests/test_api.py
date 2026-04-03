from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import AppSettings
from app.domain.enums import (
    BindingType,
    ItemStatus,
    OperationState,
    RoleCode,
    SessionStatus,
    SessionType,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.models import (
    InventoryBalance,
    Item,
    Operation,
    OperationSession,
    OperationStateHistory,
    Permission,
    RecoveryCase,
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
    _seed_base_domain(app, grant_permissions=False)

    with TestClient(app) as client:
        auth_response = client.post("/auth/resolve", json={"user_id": 1})
        inventory_response = client.get("/inventory/1/1")

    assert auth_response.status_code == 200
    assert auth_response.json()["user_code"] == "user-1"
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 5


def test_dispense_operation_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense.sqlite3"))
    _seed_base_domain(app, grant_permissions=True)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["qty_confirmed"] == 1


def test_dispense_operation_denial_maps_to_authorization_error(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_denied.sqlite3"))
    _seed_base_domain(app, grant_permissions=False)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "authorization_error"
    assert response.json()["reason_codes"] == ["dispense_permission_missing"]
    assert response.json()["detail"] == "dispense denied: dispense_permission_missing"


def test_rule_check_endpoints_return_structured_payloads(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_rules.sqlite3"))
    ids = _seed_rule_domain_with_permissions(app)

    with TestClient(app) as client:
        dispense_response = client.post(
            "/rules/dispense-check",
            json={"user_id": ids["user_id"], "item_id": ids["item_id"], "slot_id": ids["slot_id"], "quantity": 1},
        )
        return_response = client.post(
            "/rules/return-check",
            json={"user_id": ids["user_id"], "item_id": ids["item_id"], "slot_id": ids["slot_id"], "quantity": 1},
        )
        refill_response = client.post(
            "/rules/refill-check",
            json={
                "operator_user_id": ids["operator_user_id"],
                "item_id": ids["item_id"],
                "slot_id": ids["slot_id"],
                "quantity": 2,
                "session_id": ids["service_session_id"],
            },
        )

    assert dispense_response.status_code == 200
    assert dispense_response.json()["allowed"] is True
    assert dispense_response.json()["reason_codes"] == []
    assert return_response.status_code == 200
    assert return_response.json()["allowed"] is True
    assert refill_response.status_code == 200
    assert refill_response.json()["allowed"] is True
    assert refill_response.json()["rules"][-1]["code"] == "refill_session_valid"


def test_recovery_endpoints_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_recovery.sqlite3"))
    _seed_base_domain(app, grant_permissions=False)
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


def _seed_base_domain(app, *, grant_permissions: bool) -> None:
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
        if grant_permissions:
            session.add(
                Permission(
                    user_id=user.id,
                    item_id=item.id,
                    item_group_id=None,
                    can_dispense=True,
                    can_return=True,
                    valid_from=None,
                    valid_to=None,
                    comment="seeded permission",
                )
            )
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


def _seed_rule_domain_with_permissions(app) -> dict[str, int]:
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
        session.add(
            Permission(
                user_id=user.id,
                item_id=item.id,
                item_group_id=None,
                can_dispense=True,
                can_return=True,
                valid_from=None,
                valid_to=None,
                comment="seeded permission",
            )
        )
        service_session = OperationSession(
            session_type=SessionType.SERVICE,
            status=SessionStatus.ACTIVE,
            started_by_user_id=operator.id,
            started_at=None,
            finished_at=None,
            comment="seeded service session",
            context_json={},
        )
        session.add(service_session)
        session.commit()
        return {
            "user_id": user.id,
            "operator_user_id": operator.id,
            "item_id": item.id,
            "slot_id": slot.id,
            "service_session_id": service_session.id,
        }
