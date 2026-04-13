from __future__ import annotations

from pathlib import Path
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import create_app
from app.config import AppSettings, HardwareProvider
from app.domain.enums import HardwareEndpointType
from app.hardware import HardwareFacade, LockState, MockDrumAdapter, MockLockAdapter, MockRfidAdapter
from app.hardware.dto import HardwareOperationStatus, RfidReadResult
from app.hardware.factory import HardwareBundle
from app.domain.enums import (
    BindingType,
    DispenseRestrictionPolicy,
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


def test_admin_system_status_endpoint_returns_health_readiness_and_runtime_settings(tmp_path: Path) -> None:
    app = create_app(
        AppSettings(
            data_dir=tmp_path,
            sqlite_filename="api_admin_system_status.sqlite3",
            alembic_config_path=Path("alembic.ini"),
            app_name="DION ABA1 Test",
            app_environment="test",
            hardware_provider=HardwareProvider.STUB_REAL,
            api_host="0.0.0.0",
            api_port=8012,
        )
    )

    with TestClient(app) as client:
        response = client.get("/admin/system/status")

    assert response.status_code == 200
    assert response.json() == {
        "health_status": "ok",
        "readiness_status": "degraded",
        "hardware_provider": "stub-real",
        "app_environment": "test",
        "app_name": "DION ABA1 Test",
        "api_host": "0.0.0.0",
        "api_port": 8012,
    }


def test_ui_mvp_page_serves_configured_dispense_flow(tmp_path: Path) -> None:
    app = create_app(
        AppSettings(
            data_dir=tmp_path,
            sqlite_filename="api_ui_mvp.sqlite3",
            alembic_config_path=Path("alembic.ini"),
        )
    )

    with TestClient(app) as client:
        response = client.get("/ui/mvp")

    assert response.status_code == 200
    assert "Начать RFID-сканирование" in response.text
    assert "Готово к выдаче" in response.text
    assert '"/inventory/kiosk-dispense-options"' in response.text
    assert '"dispenseQuantity": 1' in response.text
    assert '"autoResetTimeoutMs": 15000' in response.text


def test_ui_admin_page_serves_user_management_config(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui/admin")

    assert response.status_code == 200
    assert "Операции, требующие внимания" in response.text
    assert "Экспорт CSV" in response.text
    assert "Админка оператора MVP" in response.text
    assert "Импорт CSV" in response.text
    assert "Импортировать CSV" in response.text
    assert "Загрузить пример" in response.text
    assert "Скачать пример CSV" in response.text
    assert "Последние действия системы" in response.text
    assert "Провайдер оборудования / режим" in response.text
    assert "Привязка API" in response.text
    assert '"/admin/users"' in response.text
    assert '"/admin/system/status"' in response.text
    assert '"/admin/operations/problem"' in response.text
    assert '"/admin/operations/recent"' in response.text
    assert '"/admin/users/import"' in response.text
    assert '"/ui-assets/admin-users-import-example.csv"' in response.text
    assert '"once_per_day"' in response.text
    assert '"/admin/users/export"' in response.text
    assert '"problemOperationsEndpoint"' in response.text
    assert '"recentOperationsEndpoint"' in response.text
    assert '"exportUsersEndpoint"' in response.text
    assert '"importExampleCsvText"' in response.text


def test_ui_mvp_static_assets_are_served(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_assets.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/mvp.js")

    assert response.status_code == 200
    assert "resetToIdle" in response.text
    assert "scheduleAutoReset" in response.text


def test_ui_admin_static_assets_are_served(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin_assets.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/admin.js")

    assert response.status_code == 200
    assert "saveRow" in response.text
    assert "loadUsers" in response.text
    assert "loadExampleCsv" in response.text
    assert "loadSystemStatus" in response.text
    assert "systemStatusEndpoint" in response.text
    assert "importUsers" in response.text
    assert "created_count" in response.text
    assert "updated_count" in response.text
    assert "total_rows" in response.text
    assert "getDisplayLabel" in response.text
    assert 'degraded: "\\u041e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u0435\\u043d\\u043d\\u0430\\u044f \\u0433\\u043e\\u0442\\u043e\\u0432\\u043d\\u043e\\u0441\\u0442\\u044c"' in response.text
    assert 'dispense: "\\u0412\\u044b\\u0434\\u0430\\u0447\\u0430"' in response.text
    assert 'recovery_required: "\\u0422\\u0440\\u0435\\u0431\\u0443\\u0435\\u0442\\u0441\\u044f \\u0432\\u043e\\u0441\\u0441\\u0442\\u0430\\u043d\\u043e\\u0432\\u043b\\u0435\\u043d\\u0438\\u0435"' in response.text
    assert 'once_per_day: "\\u041e\\u0434\\u0438\\u043d \\u0440\\u0430\\u0437 \\u0432 \\u0434\\u0435\\u043d\\u044c"' in response.text


def test_ui_admin_import_example_csv_asset_is_served(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin_import_example_asset.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/admin-users-import-example.csv")

    assert response.status_code == 200
    assert "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy" in response.text
    assert "user-1001,Ivan Petrov,user,11 22 aa bb,unlimited" in response.text
    assert "operator-2001,Anna Sidorova,operator,44 55 cc dd,once_per_day" in response.text


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


def test_available_dispense_options_endpoint_returns_stocked_active_options(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_available_dispense.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.get("/inventory/available-dispense-options")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "options": [
            {
                "slot_id": 1,
                "item_id": 1,
                "quantity": 5,
                "updated_at": payload["options"][0]["updated_at"],
                "slot_code": "slot-1",
                "drum_position": 3,
                "board_address": 1,
                "lock_number": 1,
                "item_sku": "item-1",
                "item_name": "Item One",
                "item_unit": "pcs",
            }
        ]
    }


def test_kiosk_dispense_options_endpoint_returns_aggregated_item_options(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_kiosk_dispense.sqlite3"))
    _seed_base_domain(app)
    _seed_additional_slot_for_same_item(app)

    with TestClient(app) as client:
        response = client.get("/inventory/kiosk-dispense-options")

    assert response.status_code == 200
    assert response.json() == {
        "options": [
            {
                "item_id": 1,
                "item_name": "Item One",
                "item_unit": "pcs",
                "total_quantity": 8,
            }
        ]
    }


def test_dispense_operation_resolves_first_stocked_slot_for_item_when_slot_not_provided(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_item_only.sqlite3"))
    _seed_base_domain(app)
    _seed_additional_slot_for_same_item(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "quantity": 1},
        )
        first_slot_inventory = client.get("/inventory/1/1")
        second_slot_inventory = client.get("/inventory/2/1")

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["slot_id"] == 1
    assert first_slot_inventory.status_code == 200
    assert first_slot_inventory.json()["balance"]["quantity"] == 4
    assert second_slot_inventory.status_code == 200
    assert second_slot_inventory.json()["balance"]["quantity"] == 3


def test_auth_read_and_resolve_rfid_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid.sqlite3"))
    _seed_base_domain(app)
    rfid_reader = MockRfidAdapter()
    rfid_reader.queue_card("00 0f-e2 76 7c 00 45")
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=MockDrumAdapter(),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=rfid_reader,
        facade=HardwareFacade(
            drum_controller=MockDrumAdapter(),
            lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
            rfid_reader=rfid_reader,
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)

    with TestClient(app) as client:
        response = client.post("/auth/read-and-resolve-rfid", json={})

    assert response.status_code == 200
    assert response.json() == {
        "rfid_uid": "000FE2767C0045",
        "is_duplicate": False,
        "user": {
            "user_id": 1,
            "user_code": "user-1",
            "full_name": "User One",
            "status": "active",
            "is_active": True,
            "role_code": "user",
        },
    }


def test_auth_read_and_resolve_rfid_api_retries_past_partial_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid_retry.sqlite3"))
    _seed_base_domain(app)

    class _PartialThenFullRfidReader:
        def __init__(self) -> None:
            self.reads = [
                (None, False, "Ignoring transient partial RFID read (2/7 bytes)."),
                ("000FE2767C0045", False, None),
            ]
            self.index = 0

        def ping(self):
            raise NotImplementedError

        def read_card(self):
            uid, is_duplicate, message = self.reads[min(self.index, len(self.reads) - 1)]
            self.index += 1
            return RfidReadResult(
                device_type=HardwareEndpointType.RFID_READER,
                status=HardwareOperationStatus.NO_CARD if uid is None else HardwareOperationStatus.SUCCESS,
                ok=True,
                uid=uid,
                is_duplicate=is_duplicate,
                message=message,
            )

        def clear_buffer(self):
            raise NotImplementedError

    rfid_reader = _PartialThenFullRfidReader()
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=MockDrumAdapter(),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=rfid_reader,
        facade=HardwareFacade(
            drum_controller=MockDrumAdapter(),
            lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
            rfid_reader=rfid_reader,
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)

    with TestClient(app) as client:
        response = client.post("/auth/read-and-resolve-rfid", json={})

    assert response.status_code == 200
    assert response.json()["rfid_uid"] == "000FE2767C0045"



def test_admin_users_endpoint_lists_assigned_and_unassigned_users(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_list.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with TestClient(app) as client:
        response = client.get("/admin/users")

    assert response.status_code == 200
    assert response.json() == {
        "users": [
            {
                "user_id": 1,
                "user_code": "user-1",
                "full_name": "User One",
                "status": "active",
                "is_active": True,
                "role_code": "user",
                "rfid_uid": "000FE2767C0045",
                "dispense_restriction_policy": "unlimited",
            },
            {
                "user_id": 2,
                "user_code": "operator-1",
                "full_name": "Operator One",
                "status": "active",
                "is_active": True,
                "role_code": "operator",
                "rfid_uid": None,
                "dispense_restriction_policy": "once_per_day",
            },
        ]
    }


def test_admin_recent_operations_endpoint_returns_latest_slice_newest_first(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_recent_operations.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with app.state.session_factory() as session:
        session.add_all(
            [
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=1,
                    qty_confirmed=1,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 9, 0, 0),
                    finished_at=datetime(2026, 4, 13, 9, 1, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.REFILL_ITEM,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=1,
                    slot_id=1,
                    qty_requested=5,
                    qty_confirmed=5,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 10, 0, 0),
                    finished_at=datetime(2026, 4, 13, 10, 1, 0),
                ),
            ]
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/admin/operations/recent")

    assert response.status_code == 200
    assert response.json() == {
        "operations": [
            {
                "operation_id": 2,
                "started_at": "2026-04-13T10:00:00",
                "operation_type": "refill_item",
                "operation_state": "completed",
                "user_code": "operator-1",
                "user_full_name": "Operator One",
                "item_name": "Item One",
                "quantity": 5,
                "slot_code": "slot-1",
            },
            {
                "operation_id": 1,
                "started_at": "2026-04-13T09:00:00",
                "operation_type": "dispense",
                "operation_state": "completed",
                "user_code": "user-1",
                "user_full_name": "User One",
                "item_name": "Item One",
                "quantity": 1,
                "slot_code": "slot-1",
            },
        ]
    }


def test_admin_problem_operations_endpoint_returns_failed_and_recovery_required_only(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_problem_operations.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with app.state.session_factory() as session:
        session.add_all(
            [
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=1,
                    qty_confirmed=1,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 9, 0, 0),
                    finished_at=datetime(2026, 4, 13, 9, 1, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.FAILED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=2,
                    qty_confirmed=None,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 10, 0, 0),
                    finished_at=datetime(2026, 4, 13, 10, 1, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.RETURN,
                    operation_state=OperationState.RECOVERY_REQUIRED,
                    user_id=2,
                    item_id=1,
                    slot_id=1,
                    qty_requested=3,
                    qty_confirmed=None,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 11, 0, 0),
                    finished_at=datetime(2026, 4, 13, 11, 1, 0),
                ),
            ]
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/admin/operations/problem")

    assert response.status_code == 200
    assert response.json() == {
        "operations": [
            {
                "operation_id": 3,
                "started_at": "2026-04-13T11:00:00",
                "operation_type": "return",
                "operation_state": "recovery_required",
                "user_code": "operator-1",
                "user_full_name": "Operator One",
                "item_name": "Item One",
                "quantity": 3,
                "slot_code": "slot-1",
            },
            {
                "operation_id": 2,
                "started_at": "2026-04-13T10:00:00",
                "operation_type": "dispense",
                "operation_state": "failed",
                "user_code": "user-1",
                "user_full_name": "User One",
                "item_name": "Item One",
                "quantity": 2,
                "slot_code": "slot-1",
            },
        ]
    }


def test_admin_users_export_endpoint_returns_import_compatible_csv(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_export.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with TestClient(app) as client:
        response = client.get("/admin/users/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert response.headers["content-disposition"] == 'attachment; filename="admin-users-export.csv"'
    assert response.text == "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-1,User One,user,000FE2767C0045,unlimited",
            "operator-1,Operator One,operator,,once_per_day",
            "",
        )
    )


def test_admin_update_user_assigns_rfid_uid_and_changes_policy(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_update.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with TestClient(app) as client:
        response = client.put(
            "/admin/users/2",
            json={
                "rfid_uid": "aa bb-11 22",
                "dispense_restriction_policy": "unlimited",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "user_id": 2,
            "user_code": "operator-1",
            "full_name": "Operator One",
            "status": "active",
            "is_active": True,
            "role_code": "operator",
            "rfid_uid": "AABB1122",
            "dispense_restriction_policy": "unlimited",
        }
    }


def test_admin_update_user_can_clear_rfid_uid_assignment(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_clear_uid.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.put(
            "/admin/users/1",
            json={
                "rfid_uid": "",
                "dispense_restriction_policy": "once_per_day",
            },
        )

    assert response.status_code == 200
    assert response.json()["user"]["rfid_uid"] is None
    assert response.json()["user"]["dispense_restriction_policy"] == "once_per_day"


def test_admin_users_handles_legacy_uppercase_policy_and_rewrites_lowercase_on_update(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_policy_normalize.sqlite3"))
    _seed_base_domain(app)

    with app.state.engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE users
                SET dispense_restriction_policy = 'UNLIMITED'
                WHERE id = 1
                """
            )
        )

    with TestClient(app) as client:
        list_response = client.get("/admin/users")
        update_response = client.put(
            "/admin/users/1",
            json={
                "rfid_uid": "000FE2767C0045",
                "dispense_restriction_policy": "once_per_day",
            },
        )

    assert list_response.status_code == 200
    assert list_response.json()["users"][0]["dispense_restriction_policy"] == "unlimited"
    assert update_response.status_code == 200
    assert update_response.json()["user"]["dispense_restriction_policy"] == "once_per_day"

    with app.state.engine.connect() as connection:
        persisted_policy = connection.execute(
            text("SELECT dispense_restriction_policy FROM users WHERE id = 1")
        ).scalar_one()

    assert persisted_policy == "once_per_day"


def test_admin_user_import_creates_users_from_csv(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_create.sqlite3"))
    _seed_base_domain(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-2,User Two,user,aa bb-11 22,ONCE_PER_DAY",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )
        list_response = client.get("/admin/users")

    assert response.status_code == 200
    assert response.json() == {"result": {"created_count": 1, "updated_count": 0, "total_rows": 1}}
    assert list_response.status_code == 200
    assert list_response.json()["users"] == [
        {
            "user_id": 1,
            "user_code": "user-1",
            "full_name": "User One",
            "status": "active",
            "is_active": True,
            "role_code": "user",
            "rfid_uid": "000FE2767C0045",
            "dispense_restriction_policy": "unlimited",
        },
        {
            "user_id": 2,
            "user_code": "user-2",
            "full_name": "User Two",
            "status": "active",
            "is_active": True,
            "role_code": "user",
            "rfid_uid": "AABB1122",
            "dispense_restriction_policy": "once_per_day",
        },
    ]

    with app.state.engine.connect() as connection:
        persisted_policy = connection.execute(
            text("SELECT dispense_restriction_policy FROM users WHERE user_code = 'user-2'")
        ).scalar_one()

    assert persisted_policy == "once_per_day"


def test_admin_user_import_rejects_invalid_policy(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_invalid_policy.sqlite3"))
    _seed_base_domain(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-2,User Two,user,,weekly",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "CSV row 2: invalid dispense_restriction_policy 'weekly'",
    }


def test_admin_user_import_rejects_invalid_role_code_with_allowed_values(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_invalid_role.sqlite3"))
    _seed_base_domain(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-2,User Two,manager,,once_per_day",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "CSV row 2: invalid role_code 'manager'. Allowed role_code values: admin, operator, user",
    }


def test_admin_user_import_rejects_duplicate_user_code_in_same_payload(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_duplicate_user_code.sqlite3"))
    _seed_base_domain(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-2,User Two,user,,once_per_day",
            "user-2,User Two Again,user,,unlimited",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )
        list_response = client.get("/admin/users")

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "CSV row 3: duplicate user_code user-2 in import file",
    }
    assert list_response.status_code == 200
    assert list_response.json()["users"] == [
        {
            "user_id": 1,
            "user_code": "user-1",
            "full_name": "User One",
            "status": "active",
            "is_active": True,
            "role_code": "user",
            "rfid_uid": "000FE2767C0045",
            "dispense_restriction_policy": "unlimited",
        }
    ]


def test_admin_user_import_rejects_header_mismatch_with_expected_and_received_header(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_header_mismatch.sqlite3"))
    _seed_base_domain(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,rfid_uid,role_code,dispense_restriction_policy,unexpected_column",
            "user-2,User Two,,user,once_per_day,extra",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": (
            "CSV header mismatch. Expected: "
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy. "
            "Got: user_code,full_name,rfid_uid,role_code,dispense_restriction_policy,unexpected_column"
        ),
    }


@pytest.mark.parametrize(
    ("row_text", "expected_detail"),
    (
        (
            ",User Two,user,,once_per_day",
            "CSV row 2: user_code must not be empty",
        ),
        (
            "user-2,   ,user,,once_per_day",
            "CSV row 2: full_name must not be empty",
        ),
        (
            "user-2,User Two,  ,,once_per_day",
            "CSV row 2: role_code must not be empty",
        ),
        (
            "user-2,User Two,user,,   ",
            "CSV row 2: dispense_restriction_policy must not be empty",
        ),
    ),
)
def test_admin_user_import_rejects_empty_required_fields_with_row_context(
    tmp_path: Path,
    row_text: str,
    expected_detail: str,
) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_required_field.sqlite3"))
    _seed_base_domain(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            row_text,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": expected_detail,
    }


def test_admin_user_import_updates_existing_user_by_user_code(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_update.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-1,Updated User,user,11 22 aa bb,once_per_day",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )
        list_response = client.get("/admin/users")

    assert response.status_code == 200
    assert response.json() == {"result": {"created_count": 0, "updated_count": 1, "total_rows": 1}}
    assert list_response.status_code == 200
    assert list_response.json()["users"][0] == {
        "user_id": 1,
        "user_code": "user-1",
        "full_name": "Updated User",
        "status": "active",
        "is_active": True,
        "role_code": "user",
        "rfid_uid": "1122AABB",
        "dispense_restriction_policy": "once_per_day",
    }


def test_admin_user_import_rejects_duplicate_rfid_with_uid_and_owner_detail(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_import_duplicate_rfid.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    csv_payload = "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "operator-1,Operator One,operator,00 0f-e2 76 7c 00 45,once_per_day",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/users/import",
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv; charset=utf-8"},
        )
        list_response = client.get("/admin/users")

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "CSV row 2: RFID UID '000FE2767C0045' is already assigned to user_code 'user-1' (User One)",
    }
    assert list_response.status_code == 200
    assert list_response.json()["users"] == [
        {
            "user_id": 1,
            "user_code": "user-1",
            "full_name": "User One",
            "status": "active",
            "is_active": True,
            "role_code": "user",
            "rfid_uid": "000FE2767C0045",
            "dispense_restriction_policy": "unlimited",
        },
        {
            "user_id": 2,
            "user_code": "operator-1",
            "full_name": "Operator One",
            "status": "active",
            "is_active": True,
            "role_code": "operator",
            "rfid_uid": None,
            "dispense_restriction_policy": "once_per_day",
        },
    ]


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


def test_dispense_operation_blocks_second_successful_same_day_dispense_for_once_per_day_user(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_once_per_day.sqlite3"))
    _seed_base_domain(app, user_policy=DispenseRestrictionPolicy.ONCE_PER_DAY)

    with TestClient(app) as client:
        first_response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )
        second_response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Dispense blocked: user is limited to one successful dispense per day"


def test_dispense_operation_does_not_count_failed_attempt_before_success_for_once_per_day_user(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_failed_attempt.sqlite3"))
    _seed_base_domain(app, user_policy=DispenseRestrictionPolicy.ONCE_PER_DAY)

    with app.state.session_factory() as session:
        failed_operation = Operation(
            session_id=None,
            operation_type="dispense",
            operation_state=OperationState.FAILED,
            user_id=1,
            item_id=1,
            slot_id=1,
            qty_requested=1,
            qty_confirmed=None,
            result="hardware_error",
            error_code="hardware_timeout",
            error_message="seeded failure",
            hardware_context_json={},
            business_context_json={},
            started_at=datetime(2026, 4, 10, 8, 0, 0),
            finished_at=datetime(2026, 4, 10, 8, 1, 0),
        )
        session.add(failed_operation)
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"


def test_dispense_operation_keeps_unlimited_user_unrestricted(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_unlimited.sqlite3"))
    _seed_base_domain(app, user_policy=DispenseRestrictionPolicy.UNLIMITED)

    with TestClient(app) as client:
        first_response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )
        second_response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["operation_state"] == "completed"


def test_dispense_operation_rejects_inactive_slot_item_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense_inactive_path.sqlite3"))
    _seed_base_domain(app)
    with app.state.session_factory() as session:
        binding = session.query(SlotItemBinding).filter_by(slot_id=1, item_id=1).one()
        assert binding is not None
        binding.is_active = False
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Slot/item path is not active for dispense"


def test_real_dispense_realigns_stale_slot_board_address_before_unlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    sqlite_filename = "api_real_dispense.sqlite3"
    setup_app = create_app(_settings(tmp_path, sqlite_filename))
    _seed_base_domain(setup_app)

    monkeypatch.setattr(hardware_factory, "_create_transport_client", _fake_real_dispense_transport_client)
    real_app = create_app(_real_settings(tmp_path, sqlite_filename))

    with TestClient(real_app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )
        inventory_response = client.get("/inventory/1/1")

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["hardware_context"]["slot"]["board_address"] == 0
    assert response.json()["hardware_context"]["slot"]["lock_number"] == 1
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 4


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


def _real_settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )


def _seed_base_domain(app, *, user_policy: DispenseRestrictionPolicy = DispenseRestrictionPolicy.UNLIMITED) -> None:
    with app.state.session_factory() as session:
        role = Role(code=RoleCode.USER, name="User")
        session.add(role)
        session.flush()

        user = User(
            role_id=role.id,
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=user_policy,
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
        session.add(
            UserRfidCard(
                user_id=user.id,
                card_uid="000FE2767C0045",
                is_active=True,
                issued_at=user.created_at,
                revoked_at=None,
            )
        )
        session.commit()


def _seed_unassigned_user(app) -> None:
    with app.state.session_factory() as session:
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        session.add(operator_role)
        session.flush()
        session.add(
            User(
                role_id=operator_role.id,
                user_code="operator-1",
                full_name="Operator One",
                status=UserStatus.ACTIVE,
                dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
                is_active=True,
            )
        )
        session.commit()


def _seed_additional_slot_for_same_item(app) -> None:
    with app.state.session_factory() as session:
        item = session.query(Item).filter_by(id=1).one()
        slot = Slot(
            code="slot-2",
            slot_type=SlotType.UNIVERSAL,
            drum_position=4,
            board_address=1,
            lock_number=2,
            capacity=10,
            status=SlotStatus.ACTIVE,
        )
        session.add(slot)
        session.flush()
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
        session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=3))
        session.commit()


class _FakeRealDispenseTransport:
    def __init__(self, responses: list[bytes], *, sequence_responses: list[bytes] | None = None) -> None:
        self._responses = list(responses)
        self._sequence_responses = list(sequence_responses or [])

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        if not self._responses:
            raise AssertionError("No fake transport responses remain.")
        return self._responses.pop(0)

    def send(self, payload: bytes) -> None:
        return None

    def request_sequence(
        self,
        payloads: list[bytes],
        *,
        timeout_ms: int | None = None,
        response_timeouts_ms: list[int] | None = None,
        frame_gap_timeout_ms: int | None = None,
    ) -> list[bytes]:
        if len(self._sequence_responses) < len(payloads):
            raise AssertionError("Not enough fake sequence responses remain.")
        responses = self._sequence_responses[: len(payloads)]
        del self._sequence_responses[: len(payloads)]
        return responses


def _fake_real_dispense_transport_client(config):
    if config is None:
        return None
    if config.endpoint.code == "lock-1":
        return _FakeRealDispenseTransport([bytes.fromhex("02 00 00 81 10 00 03 96")])
    if config.endpoint.code == "rfid-1":
        return _FakeRealDispenseTransport([b"PONG\n"])
    return _FakeRealDispenseTransport([], sequence_responses=[bytes.fromhex("21 AA AA C4"), bytes.fromhex("25 C0")])


def _serial_endpoint_config(*, code: str, driver_name: str, port: str) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 9600,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }


def _lock_serial_endpoint_config(*, code: str, driver_name: str, port: str, board_address: int = 0) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "protocol": {
            "board_address": board_address,
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 19200,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }


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
