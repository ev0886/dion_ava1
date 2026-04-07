from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import create_app
from app.api.dependencies import get_application_container
from app.application.composition import build_application_container
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
    UserRfidCard,
)
from app.hardware import MockRfidAdapter


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


def test_operator_ui_page_loads_with_seeded_defaults(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_ui.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/operator")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "DION ABA1 Operator UI" in response.text
    assert 'value="3"' in response.text
    assert 'value="user-1"' in response.text
    assert 'value="2"' in response.text
    assert 'value="1"' in response.text
    assert "Operator verified physical state" in response.text
    assert "Happy Path Smoke" in response.text
    assert "/recovery/cases/" in response.text


def test_auth_and_inventory_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_inventory.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        auth_response = client.post("/auth/resolve", json={"user_id": 1})
        inventory_response = client.get("/inventory/slots/1/items/1")

    assert auth_response.status_code == 200
    assert auth_response.json()["user_code"] == "user-1"
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 5
    assert inventory_response.json()["bindings"] == [
        {
            "slot_id": 1,
            "item_id": 1,
            "binding_type": "return",
            "is_active": True,
            "valid_from": None,
            "valid_to": None,
        }
    ]


def test_auth_resolve_accepts_rfid_uid(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid.sqlite3"))
    _seed_base_domain(app, with_rfid_card=True)

    with TestClient(app) as client:
        response = client.post("/auth/resolve", json={"rfid_uid": "DEMO-USER-1"})

    assert response.status_code == 200
    assert response.json()["user_id"] == 1
    assert response.json()["user_code"] == "user-1"


def test_auth_resolve_returns_404_for_unknown_rfid_uid(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid_missing.sqlite3"))
    _seed_base_domain(app, with_rfid_card=True)

    with TestClient(app) as client:
        response = client.post("/auth/resolve", json={"rfid_uid": "UNKNOWN-CARD"})

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "User not found"}


def test_auth_resolve_returns_404_for_inactive_rfid_card_mapping(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid_inactive_card.sqlite3"))
    _seed_base_domain(app, with_rfid_card=True, rfid_card_active=False)

    with TestClient(app) as client:
        response = client.post("/auth/resolve", json={"rfid_uid": "DEMO-USER-1"})

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "User not found"}


def test_auth_resolve_returns_403_for_inactive_user_with_rfid_uid(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid_inactive_user.sqlite3"))
    _seed_base_domain(app, with_rfid_card=True, user_is_active=False)

    with TestClient(app) as client:
        response = client.post("/auth/resolve", json={"rfid_uid": "DEMO-USER-1"})

    assert response.status_code == 403
    assert response.json() == {"error": "authorization_error", "detail": "User is inactive"}


def test_auth_read_and_resolve_rfid_reads_from_mock_hardware(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_read_rfid.sqlite3"))
    _seed_base_domain(app, with_rfid_card=True)
    container = _build_overridden_container(app)
    assert isinstance(container.hardware.rfid_reader, MockRfidAdapter)
    container.hardware.rfid_reader.queue_card("demo-user-1")
    app.dependency_overrides[get_application_container] = lambda: container

    try:
        with TestClient(app) as client:
            response = client.post("/auth/read-and-resolve-rfid", json={})
    finally:
        app.dependency_overrides.clear()
        container.session.close()

    assert response.status_code == 200
    assert response.json()["user_id"] == 1
    assert response.json()["user_code"] == "user-1"


def test_auth_read_and_resolve_rfid_returns_404_for_unknown_card(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_read_rfid_unknown.sqlite3"))
    _seed_base_domain(app, with_rfid_card=True)
    container = _build_overridden_container(app)
    assert isinstance(container.hardware.rfid_reader, MockRfidAdapter)
    container.hardware.rfid_reader.queue_card("missing-card")
    app.dependency_overrides[get_application_container] = lambda: container

    try:
        with TestClient(app) as client:
            response = client.post("/auth/read-and-resolve-rfid", json={})
    finally:
        app.dependency_overrides.clear()
        container.session.close()

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "User not found"}


def test_inventory_lookup_returns_404_for_missing_slot_item_pair(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_inventory_missing.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.get("/inventory/slots/1/items/999")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "detail": "Inventory balance not found for slot 1 and item 999"}


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


def test_refill_item_route_alias_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_refill_item_alias.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/refill-item",
            json={"operator_user_id": 2, "item_id": 1, "slot_id": 1, "quantity": 3, "mode": "add"},
        )
        inventory_response = client.get("/inventory/slots/1/items/1")

    assert response.status_code == 200
    assert response.json()["operation_state"] == "session_completed"
    assert response.json()["slot_id"] == 1
    assert response.json()["item_id"] == 1
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 8


def test_refill_item_route_alias_invalid_session_id_returns_404(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_refill_item_alias_invalid_session.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/refill-item",
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


def test_openapi_operation_examples_use_seeded_values_and_clear_session_guidance(tmp_path: Path) -> None:
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
    auth_user_id_example = paths["/auth/resolve"]["post"]["requestBody"]["content"]["application/json"]["examples"]["by_user_id"][
        "value"
    ]
    auth_user_code_example = paths["/auth/resolve"]["post"]["requestBody"]["content"]["application/json"]["examples"][
        "by_user_code"
    ]["value"]
    auth_rfid_example = paths["/auth/resolve"]["post"]["requestBody"]["content"]["application/json"]["examples"][
        "by_rfid_uid"
    ]["value"]
    auth_live_rfid_example = paths["/auth/read-and-resolve-rfid"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ]["default"]["value"]
    manual_resolution_example = paths["/recovery/cases/{recovery_case_id}/manual-resolution"]["post"]["requestBody"][
        "content"
    ]["application/json"]["examples"]["default"]["value"]
    dispense_schema = response.json()["components"]["schemas"]["DispenseOperationRequest"]
    return_schema = response.json()["components"]["schemas"]["ReturnOperationRequest"]
    refill_schema = response.json()["components"]["schemas"]["RefillOperationRequest"]

    assert dispense_example == {"user_id": 3, "item_id": 1, "slot_id": 1, "quantity": 1}
    assert return_example == {"user_id": 3, "item_id": 1, "quantity": 1}
    assert refill_example == {"operator_user_id": 2, "item_id": 1, "slot_id": 1, "quantity": 5, "mode": "set"}
    assert auth_user_id_example == {"user_id": 3}
    assert auth_user_code_example == {"user_code": "user-1"}
    assert auth_rfid_example == {"rfid_uid": "DEMO-USER-1"}
    assert auth_live_rfid_example == {}
    assert manual_resolution_example == {
        "operator_user_id": 2,
        "decision": "close_case",
        "comment": "Operator verified physical state",
    }
    assert dispense_schema["properties"]["session_id"]["description"].startswith("Optional operation session. Use null")
    assert return_schema["properties"]["session_id"]["description"].startswith("Optional operation session. Use null")
    assert refill_schema["properties"]["session_id"]["description"].startswith("Optional service session. Use null")
    assert {"type": "null"} in dispense_schema["properties"]["session_id"]["anyOf"]
    assert {"type": "null"} in return_schema["properties"]["session_id"]["anyOf"]
    assert {"type": "null"} in refill_schema["properties"]["session_id"]["anyOf"]
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


def test_recovery_rescan_does_not_create_new_case_after_manual_resolution(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_manual_recovery_rescan.sqlite3"))
    _seed_base_domain(app)
    _seed_recovery_operation(app)

    with TestClient(app) as client:
        first_scan = client.post("/recovery/scan")
        recovery_case_id = first_scan.json()["open_cases"][0]["recovery_case_id"]

        manual_resolution = client.post(
            f"/recovery/cases/{recovery_case_id}/manual-resolution",
            json={
                "operator_user_id": 1,
                "decision": "close_case",
                "comment": "Operator verified physical state",
            },
        )
        rescan = client.post("/recovery/scan")

    assert first_scan.status_code == 200
    assert manual_resolution.status_code == 200
    assert rescan.status_code == 200
    assert rescan.json()["candidate_operation_ids"] == []
    assert rescan.json()["open_case_count"] == 0
    assert rescan.json()["open_cases"] == []

    with app.state.session_factory() as session:
        recovery_cases = session.execute(select(RecoveryCase).order_by(RecoveryCase.id.asc())).scalars().all()
        open_cases = [case for case in recovery_cases if case.status is RecoveryStatus.OPEN]

    assert len(recovery_cases) == 1
    assert recovery_cases[0].id == recovery_case_id
    assert recovery_cases[0].status is RecoveryStatus.RESOLVED
    assert open_cases == []


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
        response = client.get("/inventory/slots/0/items/1")

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _seed_base_domain(
    app,
    *,
    with_rfid_card: bool = False,
    rfid_card_active: bool = True,
    user_is_active: bool = True,
) -> None:
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
            is_active=user_is_active,
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
        if with_rfid_card:
            session.add(
                UserRfidCard(
                    user_id=user.id,
                    card_uid="DEMO-USER-1",
                    is_active=rfid_card_active,
                    issued_at=utc_now(),
                    revoked_at=None if rfid_card_active else utc_now(),
                )
            )
        session.commit()


def _build_overridden_container(app):
    session = app.state.session_factory()
    return build_application_container(
        settings=app.state.settings,
        engine=app.state.engine,
        session_factory=app.state.session_factory,
        session=session,
    )


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
