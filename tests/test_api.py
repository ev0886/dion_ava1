from __future__ import annotations

from pathlib import Path
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import create_app
from app.application.local_usb_export_service import LocalUsbExportService
from app.application.usb_storage_service import UsbStorageDiscoveryService
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


def test_ui_user_page_serves_configured_dispense_flow(tmp_path: Path) -> None:
    app = create_app(
        AppSettings(
            data_dir=tmp_path,
            sqlite_filename="api_ui_user.sqlite3",
            alembic_config_path=Path("alembic.ini"),
        )
    )

    with TestClient(app) as client:
        response = client.get("/ui/user")

    assert response.status_code == 200
    assert "User UI" in response.text
    assert 'id="screen-title"' in response.text
    assert '"uiRole": "user"' in response.text
    assert '"uiFlowMode": "rfid-auth-shell"' in response.text
    assert '"uiIdleTimeoutMs": 30000' in response.text
    assert '"authErrorReturnTimeoutMs": 2400' in response.text
    assert '"authSuccessRouteDelayMs": 1000' in response.text
    assert '"presenceCountdownSeconds": 30' in response.text
    assert '"/auth/read-and-resolve-rfid"' in response.text
    assert '"touchRoleRoutes": {"user": "/ui/user", "operator": "/ui/operator", "admin": "/ui/admin-touch"}' in response.text
    assert '"listTouchNomenclatureEndpoint": "/touch/nomenclature"' in response.text
    assert '"emptyNomenclatureMessage": "\\u041d\\u043e\\u043c\\u0435\\u043d\\u043a\\u043b\\u0430\\u0442\\u0443\\u0440\\u0430 \\u043d\\u0435 \\u043d\\u0430\\u0441\\u0442\\u0440\\u043e\\u0435\\u043d\\u0430"' in response.text
    assert '"/inventory/kiosk-dispense-options"' not in response.text
    assert '"/operations/dispense"' not in response.text
    assert "UI-only shell" not in response.text
    assert "Mock UI routing only" not in response.text
    assert "usb-status-title" not in response.text
    assert "usb-export-operations-button" not in response.text
    assert "usb-export-users-button" not in response.text
    assert "usb-import-users-button" not in response.text
    assert '"usbStatusEndpoint"' not in response.text
    assert '"localUsbOperationsExportEndpoint"' not in response.text
    assert '"localUsbUsersExportEndpoint"' not in response.text
    assert '"localUsbUsersImportEndpoint"' not in response.text


def test_ui_operator_page_serves_role_foundation(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_operator.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui/operator")

    assert response.status_code == 200
    assert "Operator UI" in response.text
    assert "Навигация оператора по ячейкам" in response.text
    assert "4 сектора / 120 ячеек" in response.text
    assert 'id="cells-grid"' in response.text
    assert "Изъять" in response.text
    assert "Пополнить" in response.text
    assert "Выход" in response.text
    assert '"uiRole": "operator"' in response.text
    assert '"refillWorkflowStatus": "planned"' in response.text
    assert '"listTouchNomenclatureEndpoint": "/touch/nomenclature"' in response.text
    assert '"emptyNomenclatureMessage": "\\u041d\\u043e\\u043c\\u0435\\u043d\\u043a\\u043b\\u0430\\u0442\\u0443\\u0440\\u0430 \\u043d\\u0435 \\u043d\\u0430\\u0441\\u0442\\u0440\\u043e\\u0435\\u043d\\u0430"' in response.text


def test_ui_mvp_route_remains_backward_compatible_alias_to_user_ui(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_mvp_alias.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui/mvp")

    assert response.status_code == 200
    assert "User UI" in response.text
    assert '"uiRole": "user"' in response.text
    assert 'id="screen-title"' in response.text
    assert '"uiFlowMode": "rfid-auth-shell"' in response.text
    assert '"/auth/read-and-resolve-rfid"' in response.text
    assert "UI-only shell" not in response.text
    assert "Mock UI routing only" not in response.text
    assert "usb-status-title" not in response.text
    assert "usb-export-operations-button" not in response.text
    assert "usb-export-users-button" not in response.text
    assert "usb-import-users-button" not in response.text
    assert '"usbStatusEndpoint"' not in response.text
    assert '"localUsbOperationsExportEndpoint"' not in response.text
    assert '"localUsbUsersExportEndpoint"' not in response.text
    assert '"localUsbUsersImportEndpoint"' not in response.text


def test_ui_admin_page_serves_user_management_config(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui/admin")

    assert response.status_code == 200
    assert "Admin UI" in response.text
    assert "Справочник номенклатуры" in response.text
    assert "Добавить" in response.text
    assert "Операции, требующие внимания" in response.text
    assert "Экспорт CSV" in response.text
    assert "Дата с" in response.text
    assert "Дата по" in response.text
    assert "Диапазон по дням. Если дата не указана, экспорт не запускается." in response.text
    assert 'class="table-wrap table-wrap-scroll"' in response.text
    assert "Админка оператора MVP" in response.text
    assert "Импорт CSV" in response.text
    assert "Импортировать CSV" in response.text
    assert "Загрузить пример" in response.text
    assert "Скачать пример CSV" in response.text
    assert "Последние действия системы" in response.text
    assert "Провайдер оборудования / режим" in response.text
    assert "Привязка API" in response.text
    assert '"/admin/users"' in response.text
    assert '"/admin/nomenclature"' in response.text
    assert '"/admin/system/status"' in response.text
    assert '"/admin/operations/problem"' in response.text
    assert '"/admin/operations/recent"' in response.text
    assert '"/admin/operations/export"' in response.text
    assert '"/admin/users/import"' in response.text
    assert '"/ui-assets/admin-users-import-example.csv"' in response.text
    assert '"once_per_day"' in response.text
    assert '"/admin/users/export"' in response.text
    assert '"problemOperationsEndpoint"' in response.text
    assert '"recentOperationsEndpoint"' in response.text
    assert '"exportOperationsEndpoint"' in response.text
    assert '"exportUsersEndpoint"' in response.text
    assert '"listNomenclatureEndpoint"' in response.text
    assert '"createNomenclatureEndpoint"' in response.text
    assert '"updateNomenclatureEndpointBase"' in response.text
    assert '"importExampleCsvText"' in response.text
    assert '"uiRole": "admin"' in response.text


def test_ui_admin_touch_page_serves_separate_touch_shell(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin_touch.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui/admin-touch")

    assert response.status_code == 200
    assert "Admin Touch UI" in response.text
    assert 'data-view="landing"' in response.text
    assert 'data-view="export-balances-confirm"' in response.text
    assert 'data-view="export-balances-progress"' in response.text
    assert 'data-view="export-balances-success"' in response.text
    assert 'data-view="export-operations-period"' in response.text
    assert 'data-view="export-operations-confirm"' in response.text
    assert 'data-view="export-operations-progress"' in response.text
    assert 'data-view="export-operations-success"' in response.text
    assert 'type="date"' in response.text
    assert 'data-open-picker-on-touch="true"' in response.text
    assert 'data-view="export-users-confirm"' in response.text
    assert 'data-view="export-users-progress"' in response.text
    assert 'data-view="export-users-success"' in response.text
    assert 'data-action="export-balances"' in response.text
    assert 'data-action="export-operations"' in response.text
    assert 'data-action="continue-export-operations"' in response.text
    assert 'data-action="start-export-operations"' in response.text
    assert 'data-action="start-export-balances"' in response.text
    assert 'data-action="export-users"' in response.text
    assert 'data-action="start-export-users"' in response.text
    assert 'data-action="exit-admin-touch"' in response.text
    assert 'data-action="back-to-landing"' in response.text
    assert 'id="admin-touch-presence-overlay"' in response.text
    assert 'id="admin-touch-presence-overlay-countdown"' in response.text
    assert 'id="admin-touch-presence-overlay-yes"' in response.text
    assert 'id="admin-touch-presence-overlay-no"' in response.text
    assert "Выход" in response.text
    assert "Вы еще здесь?" in response.text
    assert "Администратор" in response.text
    assert "Экспорт остатков" in response.text
    assert "Экспорт операций" in response.text
    assert "Экспорт пользователей" in response.text
    assert "Импорт пользователей" in response.text
    assert '"/ui-assets/admin-touch.css?v=' in response.text
    assert '"/ui-assets/admin-touch.js?v=' in response.text
    assert '"uiRole": "admin-touch"' in response.text
    assert '"availableActions"' in response.text
    assert '"operationsDefaultDateFrom": "01.04.2026"' in response.text
    assert '"operationsDefaultDateTo": "21.04.2026"' in response.text
    assert '"successReturnDelayMs": 2400' in response.text
    assert '"uiIdleTimeoutMs": 30000' in response.text
    assert '"presenceCountdownSeconds": 30' in response.text
    assert '"startScreenRoute": "/ui/user"' in response.text
    assert '"/local/usb/export/balances"' in response.text
    assert '"/local/usb/export/operations"' in response.text
    assert '"/local/usb/export/users"' in response.text
    assert '"/local/usb/import/users/check"' in response.text
    assert '"/local/usb/import/users"' in response.text
    assert "latest system actions" not in response.text
    assert "operations requiring attention" not in response.text
    assert '"/admin/system/status"' not in response.text
    assert '"/admin/operations/recent"' not in response.text
    assert '"/admin/operations/problem"' not in response.text
    assert '"/admin/users"' not in response.text
    assert '"/admin/users/import"' not in response.text


def test_ui_admin_touch_static_assets_are_served(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin_touch_assets.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/admin-touch.css")

    assert response.status_code == 200
    assert ".admin-touch-shell" in response.text
    assert ".admin-touch-action" in response.text
    assert ".admin-touch-header" in response.text
    assert ".admin-touch-flow-card" in response.text
    assert ".admin-touch-landing-view" in response.text
    assert ".admin-touch-spinner" in response.text


def test_ui_admin_touch_javascript_asset_is_served(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin_touch_js.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/admin-touch.js")

    assert response.status_code == 200
    assert 'setView("export-balances-confirm")' in response.text
    assert 'setView("export-operations-period")' in response.text
    assert 'setView("export-operations-confirm")' in response.text
    assert 'setView("export-users-confirm")' in response.text
    assert "postJson(EXPORT_BALANCES_ENDPOINT" in response.text
    assert "postJson(EXPORT_OPERATIONS_ENDPOINT" in response.text
    assert "postJson(EXPORT_USERS_ENDPOINT" in response.text
    assert "postJson(CHECK_IMPORT_USERS_ENDPOINT" in response.text
    assert "postJson(IMPORT_USERS_ENDPOINT" in response.text
    assert "showErrorScreen" in response.text
    assert "showPresenceOverlay" in response.text
    assert "canUseSharedInactivityTimeout" in response.text
    assert "showPicker" in response.text
    assert "openNativeDatePicker" in response.text
    assert "parsePeriodInputValue" in response.text
    assert "window.location.assign(START_SCREEN_ROUTE)" in response.text
    assert 'action === "exit-admin-touch"' in response.text
    assert "operationsDefaultDateFrom" in response.text
    assert "successReturnDelayMs" in response.text


def test_ui_mvp_javascript_asset_uses_rfid_auth_and_explicit_touch_role_routes(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_mvp_js.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/mvp.js")

    assert response.status_code == 200
    assert "AUTH_READ_AND_RESOLVE_RFID_ENDPOINT" in response.text
    assert 'window.fetch(AUTH_READ_AND_RESOLVE_RFID_ENDPOINT' in response.text
    assert "TOUCH_ROLE_ROUTES" in response.text
    assert 'window.location.assign(routePath)' in response.text
    assert 'showScreen("userItemSelect")' in response.text
    assert "go-user-role" not in response.text
    assert "go-operator-role" not in response.text
    assert "go-admin-role" not in response.text
    assert "roleSelect" not in response.text


def test_ui_operator_javascript_asset_enforces_single_quarter_selection(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_operator_js.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/operator.js")

    assert response.status_code == 200
    assert "prepareSelectionForQuarter" in response.text
    assert "getSelectedQuarter" in response.text
    assert "prepareSelectionForQuarter(currentQuarter);" in response.text


def test_admin_touch_balances_export_endpoint_writes_aggregated_csv_to_usb(tmp_path: Path, monkeypatch) -> None:
    usb_mount = tmp_path / "media" / "pi" / "USB1"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        LocalUsbExportService,
        "_timestamp_now",
        staticmethod(lambda: datetime(2026, 4, 21, 10, 11, 12)),
    )
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: type("UsbStatus", (), {
            "usb_available": True,
            "mount_path": str(usb_mount),
            "readable": True,
            "writable": True,
            "device_name": "sda1",
        })(),
    )
    app = create_app(_settings(tmp_path, "api_admin_touch_balances.sqlite3"))
    _seed_base_domain(app)
    _seed_additional_slot_for_same_item(app)

    with TestClient(app) as client:
        response = client.post("/local/usb/export/balances", json={})

    assert response.status_code == 200
    exported_path = usb_mount / "balances_export_21-04-2026_10-11-12.csv"
    assert response.json() == {
        "success": True,
        "file_path": str(exported_path),
        "file_name": "balances_export_21-04-2026_10-11-12.csv",
        "mount_path": str(usb_mount),
    }
    assert exported_path.read_text(encoding="utf-8-sig") == "\n".join(
        (
            "Номенклатура,Количество",
            "Item One,8",
            "",
        )
    )


def test_admin_touch_import_users_check_returns_missing_fixed_filename_message(tmp_path: Path, monkeypatch) -> None:
    usb_mount = tmp_path / "media" / "pi" / "USB1"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: type("UsbStatus", (), {
            "usb_available": True,
            "mount_path": str(usb_mount),
            "readable": True,
            "writable": True,
            "device_name": "sda1",
        })(),
    )
    app = create_app(_settings(tmp_path, "api_admin_touch_import_check.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post("/local/usb/import/users/check", json={})

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "Файл users_import.csv не найден",
    }


def test_admin_touch_import_users_skips_existing_user_codes_and_preserves_existing_user_data(
    tmp_path: Path, monkeypatch
) -> None:
    usb_mount = tmp_path / "media" / "pi" / "USB1"
    usb_mount.mkdir(parents=True)
    (usb_mount / "users_import.csv").write_text(
        "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-1,Updated User,user,11 22 aa bb,once_per_day",
                "user-2,User Two,user,,unlimited",
            )
        ),
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: type("UsbStatus", (), {
            "usb_available": True,
            "mount_path": str(usb_mount),
            "readable": True,
            "writable": True,
            "device_name": "sda1",
        })(),
    )
    app = create_app(_settings(tmp_path, "api_admin_touch_import_users.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post("/local/usb/import/users", json={})
        users_response = client.get("/admin/users")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "file_path": str(usb_mount / "users_import.csv"),
        "file_name": "users_import.csv",
        "mount_path": str(usb_mount),
        "created_count": 1,
        "updated_count": 0,
        "total_rows": 2,
    }
    assert users_response.status_code == 200
    assert users_response.json()["users"] == [
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
            "rfid_uid": None,
            "dispense_restriction_policy": "unlimited",
        },
    ]


def test_ui_user_static_assets_no_longer_include_usb_admin_handlers(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_user_assets.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/mvp.js")

    assert response.status_code == 200
    assert "showScreen" in response.text
    assert "showTimeoutPrompt" in response.text
    assert "handleAction" in response.text
    assert "startCountdown" in response.text
    assert "scheduleIdleTimeout" in response.text
    assert "startAuth" not in response.text
    assert "startDispense" not in response.text
    assert "refreshOptions" not in response.text
    assert "scheduleAutoReset" not in response.text
    assert "authEndpoint" not in response.text
    assert "dispenseEndpoint" not in response.text
    assert "importUsersFromUsb" not in response.text
    assert "usbStatusEndpoint" not in response.text
    assert "localUsbOperationsExportEndpoint" not in response.text
    assert "localUsbUsersExportEndpoint" not in response.text
    assert "localUsbUsersImportEndpoint" not in response.text


def test_ui_mvp_static_assets_are_served(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_assets.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/mvp.js")

    assert response.status_code == 200
    assert "showScreen" in response.text
    assert "startCountdown" in response.text

def test_ui_admin_static_assets_are_served(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_admin_assets.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/ui-assets/admin.js")

    assert response.status_code == 200
    assert "saveRow" in response.text
    assert "loadUsers" in response.text
    assert "exportOperations" in response.text
    assert "buildOperationsExportUrl" in response.text
    assert "loadExampleCsv" in response.text
    assert "loadSystemStatus" in response.text
    assert "systemStatusEndpoint" in response.text
    assert "importUsers" in response.text
    assert "created_count" in response.text
    assert "updated_count" in response.text
    assert "total_rows" in response.text
    assert "Укажите даты «с» и «по» для экспорта CSV." in response.text
    assert "Ошибка экспорта CSV" in response.text
    assert "getDisplayLabel" in response.text
    assert 'name="is_active"' in response.text
    assert "active-chip" not in response.text
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


def test_auth_read_and_resolve_rfid_returns_admin_role_for_touch_routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid_admin.sqlite3"))
    _seed_base_domain(app)
    with app.state.session_factory() as session:
        role = Role(code=RoleCode.ADMIN, name="Admin")
        session.add(role)
        session.flush()
        user = User(
            role_id=role.id,
            user_code="admin-1",
            full_name="Admin One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(
            UserRfidCard(
                user_id=user.id,
                card_uid="AA11BB22CC33DD",
                is_active=True,
                issued_at=user.created_at,
                revoked_at=None,
            )
        )
        session.commit()

    rfid_reader = MockRfidAdapter()
    rfid_reader.queue_card("aa 11-bb 22 cc 33 dd")
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
    assert response.json()["rfid_uid"] == "AA11BB22CC33DD"
    assert response.json()["user"]["role_code"] == "admin"



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


def test_admin_nomenclature_endpoints_support_create_update_activate_and_deactivate(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_nomenclature.sqlite3"))

    with TestClient(app) as client:
        create_response = client.post("/admin/nomenclature", json={"name": "  Test   Item  "})
        list_response = client.get("/admin/nomenclature")
        update_response = client.put("/admin/nomenclature/1", json={"name": "Test Item Updated"})
        deactivate_response = client.post("/admin/nomenclature/1/deactivate", json={})
        reactivate_response = client.post("/admin/nomenclature/1/activate", json={})

    assert create_response.status_code == 200
    assert create_response.json() == {
        "nomenclature": {
            "id": 1,
            "name": "Test Item",
            "is_active": True,
        },
        "reactivated_existing": False,
    }
    assert list_response.status_code == 200
    assert list_response.json() == {
        "nomenclature": [
            {
                "id": 1,
                "name": "Test Item",
                "is_active": True,
            }
        ]
    }
    assert update_response.status_code == 200
    assert update_response.json() == {
        "nomenclature": {
            "id": 1,
            "name": "Test Item Updated",
            "is_active": True,
        }
    }
    assert deactivate_response.status_code == 200
    assert deactivate_response.json() == {
        "nomenclature": {
            "id": 1,
            "name": "Test Item Updated",
            "is_active": False,
        }
    }
    assert reactivate_response.status_code == 200
    assert reactivate_response.json() == {
        "nomenclature": {
            "id": 1,
            "name": "Test Item Updated",
            "is_active": True,
        }
    }


def test_admin_nomenclature_create_reactivates_existing_inactive_duplicate(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_nomenclature_reactivate.sqlite3"))

    with TestClient(app) as client:
        first_response = client.post("/admin/nomenclature", json={"name": "Test Item"})
        deactivate_response = client.post("/admin/nomenclature/1/deactivate", json={})
        second_response = client.post("/admin/nomenclature", json={"name": "  test   item  "})
        list_response = client.get("/admin/nomenclature")

    assert first_response.status_code == 200
    assert deactivate_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == {
        "nomenclature": {
            "id": 1,
            "name": "test item",
            "is_active": True,
        },
        "reactivated_existing": True,
    }
    assert list_response.status_code == 200
    assert list_response.json() == {
        "nomenclature": [
            {
                "id": 1,
                "name": "test item",
                "is_active": True,
            }
        ]
    }


def test_admin_nomenclature_create_rejects_duplicate_active_normalized_name(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_nomenclature_duplicate.sqlite3"))

    with TestClient(app) as client:
        first_response = client.post("/admin/nomenclature", json={"name": "Test Item"})
        second_response = client.post("/admin/nomenclature", json={"name": " test   item "})

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    assert second_response.json() == {
        "error": "validation_error",
        "detail": "Nomenclature name already exists",
    }


def test_touch_nomenclature_endpoint_returns_only_active_entries_sorted_by_name(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_touch_nomenclature.sqlite3"))

    with TestClient(app) as client:
        client.post("/admin/nomenclature", json={"name": "Zulu"})
        client.post("/admin/nomenclature", json={"name": "Alpha"})
        client.post("/admin/nomenclature", json={"name": "Bravo"})
        deactivate_response = client.post("/admin/nomenclature/3/deactivate", json={})
        response = client.get("/touch/nomenclature")

    assert deactivate_response.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "nomenclature": [
            {
                "id": 2,
                "name": "Alpha",
                "is_active": True,
            },
            {
                "id": 1,
                "name": "Zulu",
                "is_active": True,
            },
        ]
    }


def test_touch_nomenclature_endpoint_returns_empty_list_when_directory_is_empty(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_touch_nomenclature_empty.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/touch/nomenclature")

    assert response.status_code == 200
    assert response.json() == {"nomenclature": []}


def test_touch_ui_assets_no_longer_embed_mock_nomenclature_lists(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_touch_assets_nomenclature.sqlite3"))

    with TestClient(app) as client:
        user_js = client.get("/ui-assets/mvp.js")
        operator_js = client.get("/ui-assets/operator.js")

    assert user_js.status_code == 200
    assert operator_js.status_code == 200
    assert "loadUserItems" in user_js.text
    assert 'fetch(TOUCH_NOMENCLATURE_ENDPOINT' in user_js.text
    assert "item-1" not in user_js.text
    assert "Перчатки защитные" not in user_js.text
    assert "loadReplenishItems" in operator_js.text
    assert 'fetch(TOUCH_NOMENCLATURE_ENDPOINT' in operator_js.text
    assert "item-01" not in operator_js.text
    assert "Вода негазированная 0,5 л" not in operator_js.text


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


def test_admin_operations_export_endpoint_returns_csv_for_selected_inclusive_day_range(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_operations_export.sqlite3"))
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
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 23, 59, 0),
                    finished_at=datetime(2026, 4, 13, 23, 59, 30),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.RETURN,
                    operation_state=OperationState.FAILED,
                    user_id=2,
                    item_id=1,
                    slot_id=1,
                    qty_requested=2,
                    qty_confirmed=None,
                    result="hardware_error",
                    error_code="lock_timeout",
                    error_message="Door lock timeout",
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 14, 0, 0, 0),
                    finished_at=datetime(2026, 4, 14, 0, 1, 0),
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
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 14, 23, 59, 59),
                    finished_at=datetime(2026, 4, 15, 0, 5, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.FAILED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=3,
                    qty_confirmed=None,
                    result="hardware_error",
                    error_code="late_error",
                    error_message="Out of range row",
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 15, 0, 0, 0),
                    finished_at=datetime(2026, 4, 15, 0, 10, 0),
                ),
            ]
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/admin/operations/export?date_from=2026-04-14&date_to=2026-04-14")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv; charset=utf-8")
    assert response.headers["content-disposition"] == 'attachment; filename="admin-operations-export.csv"'
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.content.decode("utf-8-sig") == "\n".join(
        (
            "operation_id,started_at,finished_at,operation_type,operation_state,user_code,user_full_name,item_name,quantity,slot_code,result,error_code,error_message",
            "2,2026-04-14T00:00:00,2026-04-14T00:01:00,return,failed,operator-1,Operator One,Item One,2,slot-1,hardware_error,lock_timeout,Door lock timeout",
            "3,2026-04-14T23:59:59,2026-04-15T00:05:00,refill_item,completed,operator-1,Operator One,Item One,5,slot-1,ok,,",
            "",
        )
    )


def test_admin_operations_export_endpoint_rejects_reversed_date_range(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_operations_export_invalid.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/admin/operations/export?date_from=2026-04-15&date_to=2026-04-14")

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "date_from must be less than or equal to date_to",
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
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.content.decode("utf-8-sig") == "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-1,User One,user,000FE2767C0045,unlimited",
            "operator-1,Operator One,operator,,once_per_day",
            "",
        )
    )


def test_admin_users_export_endpoint_emits_utf8_bom_and_preserves_russian_text(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_export_russian.sqlite3"))
    _seed_base_domain(app)

    with app.state.session_factory() as session:
        user = session.query(User).filter_by(id=1).one()
        user.full_name = "Иван Петров"
        session.commit()

    with TestClient(app) as client:
        response = client.get("/admin/users/export")

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    exported_csv = response.content.decode("utf-8-sig")
    assert exported_csv.splitlines()[0] == "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy"
    assert "user-1,Иван Петров,user,000FE2767C0045,unlimited" in exported_csv


def test_admin_update_user_assigns_rfid_uid_and_changes_policy(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_update.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with TestClient(app) as client:
        response = client.put(
            "/admin/users/2",
            json={
                "rfid_uid": "aa bb-11 22",
                "is_active": True,
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
                "is_active": True,
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
                "is_active": True,
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


def test_admin_update_user_can_deactivate_user_and_user_stays_in_admin_list(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_deactivate.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        update_response = client.put(
            "/admin/users/1",
            json={
                "rfid_uid": "000FE2767C0045",
                "is_active": False,
                "dispense_restriction_policy": "unlimited",
            },
        )
        list_response = client.get("/admin/users")

    assert update_response.status_code == 200
    assert update_response.json() == {
        "user": {
            "user_id": 1,
            "user_code": "user-1",
            "full_name": "User One",
            "status": "inactive",
            "is_active": False,
            "role_code": "user",
            "rfid_uid": "000FE2767C0045",
            "dispense_restriction_policy": "unlimited",
        }
    }
    assert list_response.status_code == 200
    assert list_response.json()["users"][0] == {
        "user_id": 1,
        "user_code": "user-1",
        "full_name": "User One",
        "status": "inactive",
        "is_active": False,
        "role_code": "user",
        "rfid_uid": "000FE2767C0045",
        "dispense_restriction_policy": "unlimited",
    }

    with app.state.engine.connect() as connection:
        persisted = connection.execute(
            text("SELECT status, is_active FROM users WHERE id = 1")
        ).one()

    assert persisted == ("INACTIVE", 0)


def test_admin_recent_operations_keeps_deactivated_user_in_history(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_deactivate_history.sqlite3"))
    _seed_base_domain(app)

    with app.state.session_factory() as session:
        session.add(
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
                started_at=datetime(2026, 4, 13, 12, 0, 0),
                finished_at=datetime(2026, 4, 13, 12, 1, 0),
            )
        )
        session.commit()

    with TestClient(app) as client:
        deactivate_response = client.put(
            "/admin/users/1",
            json={
                "rfid_uid": "000FE2767C0045",
                "is_active": False,
                "dispense_restriction_policy": "unlimited",
            },
        )
        history_response = client.get("/admin/operations/recent")

    assert deactivate_response.status_code == 200
    assert history_response.status_code == 200
    assert history_response.json() == {
        "operations": [
            {
                "operation_id": 1,
                "started_at": "2026-04-13T12:00:00",
                "operation_type": "dispense",
                "operation_state": "completed",
                "user_code": "user-1",
                "user_full_name": "User One",
                "item_name": "Item One",
                "quantity": 1,
                "slot_code": "slot-1",
            }
        ]
    }


def test_deactivated_user_is_rejected_by_auth_and_dispense_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(_settings(tmp_path, "api_admin_deactivate_auth.sqlite3"))
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
        deactivate_response = client.put(
            "/admin/users/1",
            json={
                "rfid_uid": "000FE2767C0045",
                "is_active": False,
                "dispense_restriction_policy": "unlimited",
            },
        )
        auth_response = client.post("/auth/resolve", json={"user_id": 1})
        rfid_response = client.post("/auth/read-and-resolve-rfid", json={})
        dispense_response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert deactivate_response.status_code == 200
    assert auth_response.status_code == 403
    assert auth_response.json()["detail"] == "User is inactive"
    assert rfid_response.status_code == 403
    assert rfid_response.json()["detail"] == "User is inactive"
    assert dispense_response.status_code == 403
    assert dispense_response.json()["detail"] == "User is inactive"


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
