from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import AppSettings
from app.domain.enums import (
    BindingType,
    ItemStatus,
    OperationState,
    OperationType,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.models import (
    InventoryBalance,
    Item,
    Operation,
    OperationStateHistory,
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


def test_error_mapping_returns_400_for_validation_error(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_errors.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/inventory/0/1")

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_users_list_returns_paginated_response_shape(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_users_list.sqlite3"))
    _seed_base_domain(app)
    _seed_extra_user(app, user_code="user-2", full_name="User Two", status=UserStatus.ACTIVE)

    with TestClient(app) as client:
        response = client.get("/users", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["user_code"] == "user-2"


def test_operations_list_applies_filter_and_pagination(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operations_list.sqlite3"))
    _seed_base_domain(app)
    _seed_operation_listing_data(app)

    with TestClient(app) as client:
        response = client.get(
            "/operations",
            params={"state": "completed", "limit": 1, "offset": 1},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert payload["total"] == 2
    assert [item["operation_id"] for item in payload["items"]] == [2]
    assert payload["items"][0]["operation_state"] == "completed"


def test_authorization_error_payload_is_consistent(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_authorization_error.sqlite3"))
    _seed_base_domain(app)
    _seed_extra_user(app, user_code="blocked-user", full_name="Blocked User", status=UserStatus.BLOCKED)

    with TestClient(app) as client:
        response = client.post("/auth/resolve", json={"user_id": 2})

    assert response.status_code == 403
    payload = response.json()
    assert payload == {
        "error": "authorization_error",
        "detail": "User is blocked",
        "message": "User is blocked",
        "reason_code": "authorization_error",
        "action": None,
    }


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


def _seed_extra_user(app, *, user_code: str, full_name: str, status: UserStatus) -> None:
    with app.state.session_factory() as session:
        role = session.query(Role).filter(Role.code == RoleCode.USER).one()
        session.add(
            User(
                role_id=role.id,
                user_code=user_code,
                full_name=full_name,
                status=status,
                is_active=status is not UserStatus.INACTIVE,
            )
        )
        session.commit()


def _seed_operation_listing_data(app) -> None:
    with app.state.session_factory() as session:
        session.add_all(
            (
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=1,
                    qty_confirmed=1,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=None,
                    finished_at=None,
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.RETURN,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=1,
                    qty_confirmed=1,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=None,
                    finished_at=None,
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.REFILL_ITEM,
                    operation_state=OperationState.FAILED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=5,
                    qty_confirmed=None,
                    result="error",
                    error_code="hardware_error",
                    error_message="motor jam",
                    hardware_context_json={},
                    business_context_json={},
                    started_at=None,
                    finished_at=None,
                ),
            )
        )
        session.commit()
