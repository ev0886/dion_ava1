from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.application.time import utc_now
from app.config import AppSettings
from app.domain.enums import BindingType, ItemStatus, OperationState, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.models import (
    AuditLog,
    InventoryBalance,
    Item,
    ItemGroup,
    Operation,
    OperationStateHistory,
    Permission,
    RecoveryCase,
    Role,
    Slot,
    SlotItemBinding,
    User,
    UserRfidCard,
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


def test_error_mapping_returns_400_for_validation_error(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_errors.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/inventory/0/1")

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_management_endpoints_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_management.sqlite3"))
    _seed_management_domain(app)

    with TestClient(app) as client:
        create_user = client.post(
            "/users",
            json={
                "user_code": "api-user-2",
                "full_name": "API User Two",
                "role_id": 1,
                "actor_user_id": 1,
            },
        )
        list_users = client.get("/users")
        create_item = client.post(
            "/items",
            json={
                "sku": "api-item-2",
                "name": "API Item Two",
                "unit": "pcs",
                "item_group_id": 1,
                "actor_user_id": 1,
            },
        )

        user_id = create_user.json()["user_id"]
        item_id = create_item.json()["item_id"]

        update_user = client.patch(f"/users/{user_id}", json={"is_active": False, "actor_user_id": 1})
        update_item = client.patch(f"/items/{item_id}", json={"is_active": False, "actor_user_id": 1})
        get_user = client.get(f"/users/{user_id}")
        get_item = client.get(f"/items/{item_id}")
        list_items = client.get("/items")
        assign_permission = client.post(
            "/permissions",
            json={"user_id": user_id, "item_id": item_id, "can_dispense": True, "actor_user_id": 1},
        )
        list_permissions = client.get(f"/users/{user_id}/permissions")
        revoke_permission = client.request(
            "DELETE",
            f"/permissions/{assign_permission.json()['permission_id']}",
            json={"actor_user_id": 1},
        )

    assert create_user.status_code == 200
    assert list_users.status_code == 200
    assert create_item.status_code == 200
    assert update_user.status_code == 200
    assert update_user.json()["status"] == "inactive"
    assert update_item.status_code == 200
    assert update_item.json()["status"] == "inactive"
    assert get_user.status_code == 200
    assert get_user.json()["user_code"] == "api-user-2"
    assert get_item.status_code == 200
    assert get_item.json()["sku"] == "api-item-2"
    assert list_items.status_code == 200
    assert len(list_items.json()["items"]) >= 1
    assert assign_permission.status_code == 200
    assert list_permissions.status_code == 200
    assert len(list_permissions.json()["permissions"]) == 1
    assert revoke_permission.status_code == 200
    assert revoke_permission.json()["is_active"] is False


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


def _seed_management_domain(app) -> None:
    with app.state.session_factory() as session:
        role = Role(code=RoleCode.ADMIN, name="Admin")
        item_group = ItemGroup(code="api-group", name="API Group", description=None, is_active=True)
        session.add_all((role, item_group))
        session.flush()
        user = User(
            role_id=role.id,
            user_code="api-admin",
            full_name="API Admin",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        item = Item(
            item_group_id=item_group.id,
            sku="api-item-1",
            name="API Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=1,
            status=ItemStatus.ACTIVE,
        )
        slot = Slot(
            code="api-slot-1",
            slot_type=SlotType.UNIVERSAL,
            drum_position=1,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((user, item, slot))
        session.flush()
        session.add(
            UserRfidCard(
                user_id=user.id,
                card_uid="CARD-001",
                is_active=True,
                issued_at=utc_now(),
                revoked_at=None,
            )
        )
        session.add(
            SlotItemBinding(
                slot_id=slot.id,
                item_id=item.id,
                binding_type=BindingType.PRIMARY,
                is_active=True,
                valid_from=None,
                valid_to=None,
            )
        )
        session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=9))
        session.commit()
