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


def test_ui_role_routes_render_and_mvp_alias_matches_user(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_routes.sqlite3"))

    with TestClient(app) as client:
        user_response = client.get("/ui/user")
        alias_response = client.get("/ui/mvp")
        operator_response = client.get("/ui/operator")
        admin_response = client.get("/ui/admin")

    assert user_response.status_code == 200
    assert alias_response.status_code == 200
    assert operator_response.status_code == 200
    assert admin_response.status_code == 200
    assert user_response.text == alias_response.text
    assert "User Workflow" in user_response.text
    assert "Operator Replenishment" in operator_response.text
    assert "Admin Console" in admin_response.text


def test_operator_replenishment_overview_lists_active_options(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_replenishment_overview.sqlite3"))
    _seed_operator_domain(app)

    with TestClient(app) as client:
        response = client.get("/inventory/replenishment-overview")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["options"]) == 2
    assert payload["options"][0]["item_name"] == "Filter Cartridge"
    assert payload["options"][0]["quantity"] == 2
    assert payload["options"][0]["slot_code"] == "slot-a1"


def test_operator_refill_updates_balance_and_overview(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_refill.sqlite3"))
    _seed_operator_domain(app)

    with TestClient(app) as client:
        refill_response = client.post(
            "/operations/refill",
            json={
                "operator_user_id": 1,
                "item_id": 1,
                "slot_id": 1,
                "quantity": 3,
                "mode": "add",
            },
        )
        overview_response = client.get("/inventory/replenishment-overview")

    assert refill_response.status_code == 200
    assert refill_response.json()["operation_state"] == "session_completed"
    assert refill_response.json()["qty_confirmed"] == 3

    assert overview_response.status_code == 200
    options = overview_response.json()["options"]
    replenished_option = next(option for option in options if option["item_id"] == 1 and option["slot_id"] == 1)
    assert replenished_option["quantity"] == 5


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


def _seed_operator_domain(app) -> None:
    with app.state.session_factory() as session:
        user_role = Role(code=RoleCode.USER, name="User")
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        session.add_all((user_role, operator_role))
        session.flush()

        operator = User(
            role_id=operator_role.id,
            user_code="operator-1",
            full_name="Operator One",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        session.add(operator)

        item_a = Item(
            item_group_id=None,
            sku="filter-01",
            name="Filter Cartridge",
            description=None,
            unit="pcs",
            return_allowed=False,
            min_level=2,
            status=ItemStatus.ACTIVE,
        )
        item_b = Item(
            item_group_id=None,
            sku="glove-02",
            name="Work Gloves",
            description=None,
            unit="pairs",
            return_allowed=True,
            min_level=1,
            status=ItemStatus.ACTIVE,
        )
        slot_a = Slot(
            code="slot-a1",
            slot_type=SlotType.UNIVERSAL,
            drum_position=1,
            board_address=1,
            lock_number=1,
            capacity=12,
            status=SlotStatus.ACTIVE,
        )
        slot_b = Slot(
            code="slot-b2",
            slot_type=SlotType.UNIVERSAL,
            drum_position=2,
            board_address=1,
            lock_number=2,
            capacity=20,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((item_a, item_b, slot_a, slot_b))
        session.flush()

        session.add_all(
            (
                SlotItemBinding(
                    slot_id=slot_a.id,
                    item_id=item_a.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
                SlotItemBinding(
                    slot_id=slot_b.id,
                    item_id=item_b.id,
                    binding_type=BindingType.RETURN,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
            )
        )
        session.add_all(
            (
                InventoryBalance(slot_id=slot_a.id, item_id=item_a.id, quantity=2),
                InventoryBalance(slot_id=slot_b.id, item_id=item_b.id, quantity=7),
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
