from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import AppSettings
from app.domain.enums import BindingType, ItemStatus, OperationState, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.models import InventoryBalance, Item, Operation, OperationStateHistory, RecoveryCase, Role, Slot, SlotItemBinding, User


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
    app = create_app(_settings(tmp_path, "api_dispense.sqlite3", auth_static_tokens={"token-user-1": "user-1"}))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            headers={"Authorization": "Bearer token-user-1"},
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["qty_confirmed"] == 1


def test_recovery_endpoints_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_recovery.sqlite3", auth_static_tokens={"token-operator-1": "operator-1"}))
    _seed_base_domain(app)
    _seed_recovery_operation(app)

    with TestClient(app) as client:
        scan_response = client.post("/recovery/scan", headers={"X-API-Key": "token-operator-1"})

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


def test_authenticated_admin_access_to_export_route(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_export.sqlite3", auth_static_tokens={"token-admin-1": "admin-1"}))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/exports/create",
            headers={"Authorization": "Bearer token-admin-1"},
            json={"requested_by_user_id": 2},
        )

    assert response.status_code == 200
    assert response.json()["requested_by_user_id"] == 2
    assert response.json()["status"] == "pending"


def test_authenticated_operator_access_to_service_mode_route(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_service_mode.sqlite3", auth_static_tokens={"token-operator-1": "operator-1"}))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/service-mode/start",
            headers={"Authorization": "Bearer token-operator-1"},
            json={"user_id": 3, "comment": "maintenance"},
        )

    assert response.status_code == 200
    assert response.json()["started_by_user_id"] == 3
    assert response.json()["status"] == "active"


def test_protected_route_rejects_missing_credentials(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_missing_credentials.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post("/operations/dispense", json={"item_id": 1, "slot_id": 1, "quantity": 1})

    assert response.status_code == 401
    assert response.json() == {"error": "authentication_error", "detail": "Missing credentials"}


def test_protected_route_rejects_invalid_credentials(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_invalid_credentials.sqlite3", auth_static_tokens={"token-user-1": "user-1"}))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            headers={"Authorization": "Bearer wrong-token"},
            json={"item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 401
    assert response.json() == {"error": "authentication_error", "detail": "Invalid credentials"}


def test_blocked_actor_is_rejected_even_with_valid_credential(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path, "api_blocked_credentials.sqlite3", auth_static_tokens={"token-blocked-1": "blocked-1"})
    )
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            headers={"Authorization": "Bearer token-blocked-1"},
            json={"item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 403
    assert response.json() == {"error": "authorization_error", "detail": "User is blocked"}


def test_transport_actor_conflict_with_payload_actor_is_rejected(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_actor_conflict.sqlite3", auth_static_tokens={"token-user-1": "user-1"}))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            headers={"Authorization": "Bearer token-user-1"},
            json={"user_id": 2, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 409
    assert response.json() == {
        "error": "actor_conflict",
        "detail": "user_id does not match authenticated actor",
    }


def test_unprotected_routes_remain_open(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_open_routes.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        health_response = client.get("/health")
        inventory_response = client.get("/inventory/1/1")

    assert health_response.status_code == 200
    assert inventory_response.status_code == 200


def test_transport_actor_can_replace_legacy_payload_actor_id(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_transport_actor.sqlite3", auth_static_tokens={"token-user-1": "user-1"}))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            headers={"Authorization": "Bearer token-user-1"},
            json={"item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 200
    assert response.json()["user_id"] == 1


def _settings(tmp_path: Path, sqlite_filename: str, auth_static_tokens: dict[str, str] | None = None) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
        auth_static_tokens=auth_static_tokens or {},
    )


def _seed_base_domain(app) -> None:
    with app.state.session_factory() as session:
        user_role = Role(code=RoleCode.USER, name="User")
        admin_role = Role(code=RoleCode.ADMIN, name="Admin")
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        session.add_all((user_role, admin_role, operator_role))
        session.flush()

        user = User(
            role_id=user_role.id,
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        admin = User(
            role_id=admin_role.id,
            user_code="admin-1",
            full_name="Admin One",
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
        blocked = User(
            role_id=user_role.id,
            user_code="blocked-1",
            full_name="Blocked User",
            status=UserStatus.BLOCKED,
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
        session.add_all((user, admin, operator, blocked, item, slot))
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
