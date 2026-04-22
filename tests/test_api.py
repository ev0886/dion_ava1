from __future__ import annotations

from pathlib import Path
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.api import create_app
from app.application.local_usb_export_service import LocalUsbExportService
from app.application.usb_storage_service import UsbStorageDiscoveryService
from app.config import AppSettings, HardwareProvider
from app.domain.enums import HardwareEndpointType
from app.hardware import HardwareFacade, LockState, MockDrumAdapter, MockHardwareMode, MockLockAdapter, MockRfidAdapter
from app.hardware.dto import HardwareOperationStatus, RfidReadResult
from app.hardware.factory import HardwareBundle
from app.domain.enums import (
    BindingType,
    DispenseRestrictionPolicy,
    InventoryTransactionType,
    ItemStatus,
    OperationState,
    OperationType,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.models import (
    EventLog,
    InventoryBalance,
    InventoryTransaction,
    Item,
    NomenclatureEntry,
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


def test_admin_system_status_endpoint_returns_compact_admin_summary(tmp_path: Path) -> None:
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
    payload = response.json()
    assert payload["api_available"] is True
    assert payload["hardware_status"] == "error"
    assert payload["hardware_mode"] == "mock"
    assert payload["open_cells"] is False
    assert isinstance(payload["checked_at"], str)


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
    assert '"userDispenseOptionsEndpoint": "/user/dispense-options"' in response.text
    assert '"userDispenseSubmitEndpoint": "/user/dispense"' in response.text
    assert '"userDoorStatusEndpoint": "/user/door-status"' in response.text
    assert '"userDoorStatusPollIntervalMs": 300' in response.text
    assert '"emptyNomenclatureMessage": "\\u041d\\u043e\\u043c\\u0435\\u043d\\u043a\\u043b\\u0430\\u0442\\u0443\\u0440\\u0430 \\u043d\\u0435 \\u043d\\u0430\\u0441\\u0442\\u0440\\u043e\\u0435\\u043d\\u0430"' in response.text
    assert '"/touch/nomenclature"' not in response.text
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
    assert "РќР°РІРёРіР°С†РёСЏ РѕРїРµСЂР°С‚РѕСЂР° РїРѕ СЏС‡РµР№РєР°Рј" in response.text
    assert "4 СЃРµРєС‚РѕСЂР° / 120 СЏС‡РµРµРє" in response.text
    assert 'id="cells-grid"' in response.text
    assert "РР·СЉСЏС‚СЊ" in response.text
    assert "РџРѕРїРѕР»РЅРёС‚СЊ" in response.text
    assert "Р’С‹С…РѕРґ" in response.text
    assert '"uiRole": "operator"' in response.text
    assert '"refillWorkflowStatus": "real-db-no-hardware"' in response.text
    assert '"touchAuthStorageKey": "dion.touchAuthContext"' in response.text
    assert '"listTouchNomenclatureEndpoint": "/touch/nomenclature"' in response.text
    assert '"operatorBoardStateEndpoint": "/operator/board"' in response.text
    assert '"operatorPrepareReplenishEndpoint": "/operator/inventory/replenish/prepare"' in response.text
    assert '"operatorReplenishEndpoint": "/operator/inventory/replenish"' in response.text
    assert '"operatorPrepareRemoveEndpoint": "/operator/inventory/remove/prepare"' in response.text
    assert '"operatorRemoveEndpoint": "/operator/inventory/remove"' in response.text
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
    assert "РЎРїСЂР°РІРѕС‡РЅРёРє РЅРѕРјРµРЅРєР»Р°С‚СѓСЂС‹" in response.text
    assert "Р”РѕР±Р°РІРёС‚СЊ" in response.text
    assert "РћРїРµСЂР°С†РёРё, С‚СЂРµР±СѓСЋС‰РёРµ РІРЅРёРјР°РЅРёСЏ" in response.text
    assert "Р­РєСЃРїРѕСЂС‚ CSV" in response.text
    assert "Р”Р°С‚Р° СЃ" in response.text
    assert "Р”Р°С‚Р° РїРѕ" in response.text
    assert "Р”РёР°РїР°Р·РѕРЅ РїРѕ РґРЅСЏРј. Р•СЃР»Рё РґР°С‚Р° РЅРµ СѓРєР°Р·Р°РЅР°, СЌРєСЃРїРѕСЂС‚ РЅРµ Р·Р°РїСѓСЃРєР°РµС‚СЃСЏ." in response.text
    assert 'class="table-wrap table-wrap-scroll"' in response.text
    assert "РђРґРјРёРЅРёСЃС‚СЂРёСЂРѕРІР°РЅРёРµ РІРµРЅРґРёРЅРіРѕРІРѕРіРѕ Р°РїРїР°СЂР°С‚Р° DION" in response.text
    assert "РђРґРјРёРЅРєР° РѕРїРµСЂР°С‚РѕСЂР° MVP" not in response.text
    assert "РРјРїРѕСЂС‚ CSV" in response.text
    assert "РРјРїРѕСЂС‚РёСЂРѕРІР°С‚СЊ CSV" in response.text
    assert "Р—Р°РіСЂСѓР·РёС‚СЊ РїСЂРёРјРµСЂ" in response.text
    assert "РЎРєР°С‡Р°С‚СЊ РїСЂРёРјРµСЂ CSV" in response.text
    assert "РџРѕСЃР»РµРґРЅРёРµ РґРµР№СЃС‚РІРёСЏ СЃРёСЃС‚РµРјС‹" in response.text
    assert "РЎРѕСЃС‚РѕСЏРЅРёРµ API" in response.text
    assert "РћР±РѕСЂСѓРґРѕРІР°РЅРёРµ" in response.text
    assert "Р РµР¶РёРј РѕР±РѕСЂСѓРґРѕРІР°РЅРёСЏ" in response.text
    assert "РћС‚РєСЂС‹С‚С‹Рµ СЏС‡РµР№РєРё" in response.text
    assert "РџРѕСЃР»РµРґРЅСЏСЏ РїСЂРѕРІРµСЂРєР°" in response.text
    assert "РџСЂРёРІСЏР·РєР° API" not in response.text
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
    assert '"createUserEndpoint"' in response.text
    assert '"listNomenclatureEndpoint"' in response.text
    assert '"createNomenclatureEndpoint"' in response.text
    assert '"updateNomenclatureEndpointBase"' in response.text
    assert '"importExampleCsvText"' in response.text
    assert '"supportedRoles"' in response.text
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
    assert "Р’С‹С…РѕРґ" in response.text
    assert "Р’С‹ РµС‰Рµ Р·РґРµСЃСЊ?" in response.text
    assert "РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ" in response.text
    assert "Р­РєСЃРїРѕСЂС‚ РѕСЃС‚Р°С‚РєРѕРІ" in response.text
    assert "Р­РєСЃРїРѕСЂС‚ РѕРїРµСЂР°С†РёР№" in response.text
    assert "Р­РєСЃРїРѕСЂС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№" in response.text
    assert "РРјРїРѕСЂС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»РµР№" in response.text
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
    assert "USER_DISPENSE_OPTIONS_ENDPOINT" in response.text
    assert "USER_DISPENSE_SUBMIT_ENDPOINT" in response.text
    assert "USER_DOOR_STATUS_ENDPOINT" in response.text
    assert "USER_DOOR_STATUS_POLL_INTERVAL_MS" in response.text
    assert "buildTouchAuthContext" in response.text
    assert "loadUserItemsForResolvedUser" in response.text
    assert '"\\u0417\\u0430\\u0431\\u0435\\u0440\\u0438\\u0442\\u0435 \\u0442\\u043e\\u0432\\u0430\\u0440 \\u0438 \\u0437\\u0430\\u043a\\u0440\\u043e\\u0439\\u0442\\u0435 \\u044f\\u0447\\u0435\\u0439\\u043a\\u0443!"' in response.text
    assert '"\\u0417\\u0430\\u043a\\u0440\\u043e\\u0439\\u0442\\u0435 \\u043e\\u0442\\u043a\\u0440\\u044b\\u0442\\u044b\\u0435 \\u044f\\u0447\\u0435\\u0439\\u043a\\u0438"' in response.text
    assert "const userId = Number(resolvedUser.user_id);" in response.text
    assert "Number.isFinite(userId)" in response.text
    assert 'window.sessionStorage.setItem(TOUCH_AUTH_STORAGE_KEY, JSON.stringify(authContext));' in response.text
    assert 'window.location.assign(routePath)' in response.text
    assert 'showScreen("userItemSelect")' in response.text
    assert "isCompletedUserDispense" in response.text
    assert "resolveTargetDoorFromDispensePayload" in response.text
    assert "pollTargetDoorStatus" in response.text
    assert 'showScreen("userItemAvailable")' in response.text
    assert 'if (!response.ok || !isCompletedUserDispense(payload)) {' in response.text
    assert 'if (response.status === 400 && payload && payload.detail === "Authorization blocked: one or more cells are open") {' in response.text
    assert 'showScreen("userItemSuccess")' in response.text
    assert "await loadUserItemsForResolvedUser();" not in response.text
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
    assert "isCellSelectable" in response.text


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
            "РќРѕРјРµРЅРєР»Р°С‚СѓСЂР°,РљРѕР»РёС‡РµСЃС‚РІРѕ",
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
        "detail": "Р¤Р°Р№Р» users_import.csv РЅРµ РЅР°Р№РґРµРЅ",
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
    assert "РЈРєР°Р¶РёС‚Рµ РґР°С‚С‹ В«СЃВ» Рё В«РїРѕВ» РґР»СЏ СЌРєСЃРїРѕСЂС‚Р° CSV." in response.text
    assert "РћС€РёР±РєР° СЌРєСЃРїРѕСЂС‚Р° CSV" in response.text
    assert "getDisplayLabel" in response.text
    assert 'name="is_active"' in response.text
    assert "active-chip" not in response.text
    assert "createUser" in response.text
    assert 'available: "\\u041e\\u043d\\u043b\\u0430\\u0439\\u043d"' in response.text
    assert 'error: "\\u0415\\u0441\\u0442\\u044c \\u043e\\u0448\\u0438\\u0431\\u043a\\u0438"' in response.text
    assert 'dispense: "\\u0412\\u044b\\u0434\\u0430\\u0447\\u0430"' in response.text
    assert 'recovery_required: "\\u0422\\u0440\\u0435\\u0431\\u0443\\u0435\\u0442\\u0441\\u044f \\u043f\\u0440\\u043e\\u0432\\u0435\\u0440\\u043a\\u0430"' in response.text
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


def test_user_dispense_options_endpoint_returns_real_aggregated_available_items(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_user_dispense_options.sqlite3"))
    _seed_base_domain(app)
    _seed_additional_slot_for_same_item(app)

    with TestClient(app) as client:
        response = client.get("/user/dispense-options", params={"user_id": 1})

    assert response.status_code == 200
    assert response.json() == {
        "options": [
            {
                "item_id": 1,
                "item_name": "Item One",
                "item_unit": "pcs",
                "total_quantity": 8,
            }
        ],
        "restriction_blocked": False,
        "unavailable_reason": None,
    }


def test_user_dispense_options_endpoint_orders_items_by_logical_sector_number(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_user_dispense_options_logical_order.sqlite3"))

    with app.state.session_factory() as session:
        role = Role(code=RoleCode.USER, name="User")
        session.add(role)
        session.flush()

        user = User(
            role_id=role.id,
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
            is_active=True,
        )
        first_item = Item(
            item_group_id=None,
            sku="item-z",
            name="Zulu Item",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        second_item = Item(
            item_group_id=None,
            sku="item-a",
            name="Alpha Item",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        third_item = Item(
            item_group_id=None,
            sku="item-m",
            name="Mike Item",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        session.add_all((user, first_item, second_item, third_item))
        session.flush()

        slots = (
            Slot(
                code="slot-p00-l01",
                slot_type=SlotType.UNIVERSAL,
                drum_position=0,
                board_address=1,
                lock_number=1,
                capacity=10,
                status=SlotStatus.ACTIVE,
            ),
            Slot(
                code="slot-p31-l01",
                slot_type=SlotType.UNIVERSAL,
                drum_position=31,
                board_address=1,
                lock_number=1,
                capacity=10,
                status=SlotStatus.ACTIVE,
            ),
            Slot(
                code="slot-p30-l01",
                slot_type=SlotType.UNIVERSAL,
                drum_position=30,
                board_address=1,
                lock_number=1,
                capacity=10,
                status=SlotStatus.ACTIVE,
            ),
        )
        session.add_all(slots)
        session.flush()

        session.add_all(
            (
                SlotItemBinding(
                    slot_id=slots[0].id,
                    item_id=first_item.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
                SlotItemBinding(
                    slot_id=slots[1].id,
                    item_id=second_item.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
                SlotItemBinding(
                    slot_id=slots[2].id,
                    item_id=third_item.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
                InventoryBalance(slot_id=slots[0].id, item_id=first_item.id, quantity=1),
                InventoryBalance(slot_id=slots[1].id, item_id=second_item.id, quantity=1),
                InventoryBalance(slot_id=slots[2].id, item_id=third_item.id, quantity=1),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/user/dispense-options", params={"user_id": 1})

    assert response.status_code == 200
    assert [option["item_name"] for option in response.json()["options"]] == [
        "Zulu Item",
        "Alpha Item",
        "Mike Item",
    ]


def test_user_dispense_options_endpoint_returns_empty_when_user_policy_blocks_dispense(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_user_dispense_options_blocked.sqlite3"))
    _seed_base_domain(app, user_policy=DispenseRestrictionPolicy.ONCE_PER_DAY)

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
                result="completed",
                error_code=None,
                error_message=None,
                hardware_context_json={},
                business_context_json={},
                started_at=datetime(2026, 4, 22, 8, 0, 0),
                finished_at=datetime(2026, 4, 22, 8, 1, 0),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/user/dispense-options", params={"user_id": 1})

    assert response.status_code == 200
    assert response.json() == {
        "options": [],
        "restriction_blocked": True,
        "unavailable_reason": "Dispense blocked: user is limited to one successful dispense per day",
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


def test_user_dispense_endpoint_resolves_first_logically_numbered_slot_and_debits_single_quantity_via_hardware_path(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path, "api_user_dispense.sqlite3"))
    _seed_base_domain(app)
    _seed_additional_slot_for_same_item(app)

    with TestClient(app) as client:
        response = client.post(
            "/user/dispense",
            json={"user_id": 1, "item_id": 1, "quantity": 1},
        )
        first_slot_inventory = client.get("/inventory/1/1")
        second_slot_inventory = client.get("/inventory/2/1")

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["slot_id"] == 2
    assert response.json()["hardware_context"]["slot"] == {
        "drum_position": 4,
        "board_address": 1,
        "lock_number": 2,
    }
    assert first_slot_inventory.status_code == 200
    assert first_slot_inventory.json()["balance"]["quantity"] == 5
    assert second_slot_inventory.status_code == 200
    assert second_slot_inventory.json()["balance"]["quantity"] == 2

    with app.state.session_factory() as session:
        operation = session.query(Operation).filter_by(id=response.json()["operation_id"]).one()
        history = session.query(OperationStateHistory).filter_by(operation_id=operation.id).all()
        transaction = session.query(InventoryTransaction).filter_by(operation_id=operation.id).one()

    assert operation.operation_type == OperationType.DISPENSE
    assert operation.operation_state == OperationState.COMPLETED
    assert len(history) >= 10
    assert transaction.quantity_before == 3
    assert transaction.quantity_after == 2
    assert transaction.quantity_delta == -1
    assert transaction.transaction_type == "dispense_debit"


def test_user_dispense_endpoint_rejects_when_selected_item_no_longer_has_filled_slot(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_user_dispense_empty.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        responses = [
            client.post(
                "/user/dispense",
                json={"user_id": 1, "item_id": 1, "quantity": 1},
            )
            for _ in range(6)
        ]

    assert all(response.status_code == 200 for response in responses[:5])
    assert responses[5].status_code == 404
    assert responses[5].json()["detail"] == "No available dispense slot found for item: 1"


def test_real_user_dispense_uses_existing_real_hardware_path_and_only_mutates_inventory_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    sqlite_filename = "api_real_user_dispense.sqlite3"
    setup_app = create_app(_settings(tmp_path, sqlite_filename))
    _seed_base_domain(setup_app)
    _seed_additional_slot_for_same_item(setup_app)

    monkeypatch.setattr(hardware_factory, "_create_transport_client", _fake_real_dispense_transport_client)
    real_app = create_app(_real_settings(tmp_path, sqlite_filename))

    with TestClient(real_app) as client:
        response = client.post(
            "/user/dispense",
            json={"user_id": 1, "item_id": 1, "quantity": 1},
        )
        first_slot_inventory = client.get("/inventory/1/1")
        second_slot_inventory = client.get("/inventory/2/1")

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["slot_id"] == 1
    assert response.json()["hardware_context"]["slot"]["board_address"] == 0
    assert response.json()["hardware_context"]["slot"]["lock_number"] == 1
    assert first_slot_inventory.status_code == 200
    assert first_slot_inventory.json()["balance"]["quantity"] == 4
    assert second_slot_inventory.status_code == 200
    assert second_slot_inventory.json()["balance"]["quantity"] == 3


def test_user_dispense_returns_hardware_failure_without_inventory_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=MockDrumAdapter(move_mode=MockHardwareMode.TIMEOUT),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=MockRfidAdapter(),
        facade=HardwareFacade(
            drum_controller=MockDrumAdapter(move_mode=MockHardwareMode.TIMEOUT),
            lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
            rfid_reader=MockRfidAdapter(),
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)

    app = create_app(_settings(tmp_path, "api_user_dispense_hardware_failure.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/user/dispense",
            json={"user_id": 1, "item_id": 1, "quantity": 1},
        )
        inventory_response = client.get("/inventory/1/1")

    assert response.status_code == 200
    assert response.json()["operation_state"] == "failed"
    assert response.json()["result"] == "hardware_error"
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 5


def test_user_door_status_endpoint_reports_real_target_lock_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hardware_bundle = _open_door_hardware_bundle(board_address=1, lock_number=1)
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_user_door_status.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.get("/user/door-status", params={"board_address": 1, "lock_number": 1})

    assert response.status_code == 200
    assert response.json() == {
        "board_address": 1,
        "lock_number": 1,
        "lock_state": "open",
        "is_open": True,
        "is_closed": False,
    }


def test_open_door_guard_blocks_auth_and_user_dispense_flow_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hardware_bundle = _open_door_hardware_bundle(board_address=1, lock_number=1)
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_open_door_user_flow_block.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        auth_resolve_response = client.post("/auth/resolve", json={"user_id": 1})
        auth_rfid_response = client.post("/auth/read-and-resolve-rfid", json={})
        options_response = client.get("/user/dispense-options", params={"user_id": 1})
        user_dispense_response = client.post("/user/dispense", json={"user_id": 1, "item_id": 1, "quantity": 1})
        dispense_response = client.post("/operations/dispense", json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1})
        return_response = client.post("/operations/return", json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1})

    assert auth_resolve_response.status_code == 400
    assert auth_resolve_response.json()["detail"] == "Authorization blocked: one or more cells are open"
    assert auth_rfid_response.status_code == 400
    assert auth_rfid_response.json()["detail"] == "Authorization blocked: one or more cells are open"
    assert options_response.status_code == 200
    assert options_response.json() == {
        "options": [],
        "restriction_blocked": True,
        "unavailable_reason": "Dispense blocked: one or more cells are open",
    }
    assert user_dispense_response.status_code == 400
    assert user_dispense_response.json()["detail"] == "Dispense blocked: one or more cells are open"
    assert dispense_response.status_code == 400
    assert dispense_response.json()["detail"] == "Dispense blocked: one or more cells are open"
    assert return_response.status_code == 400
    assert return_response.json()["detail"] == "Return blocked: one or more cells are open"


def test_open_door_guard_blocks_operator_and_refill_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hardware_bundle = _open_door_hardware_bundle(board_address=0, lock_number=1)
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_open_door_operator_flow_block.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        prepare_replenish_response = client.post(
            "/operator/inventory/replenish/prepare",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_two_id],
            },
        )
        replenish_response = client.post(
            "/operator/inventory/replenish",
            json={
                "operator_user_id": ids.operator_user_id,
                "nomenclature_id": ids.nomenclature_id,
                "slot_ids": [ids.slot_two_id],
            },
        )
        prepare_remove_response = client.post(
            "/operator/inventory/remove/prepare",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_one_id],
            },
        )
        remove_response = client.post(
            "/operator/inventory/remove",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_one_id],
            },
        )
        refill_response = client.post(
            "/operations/refill",
            json={
                "operator_user_id": ids.operator_user_id,
                "item_id": ids.item_id,
                "slot_id": ids.slot_one_id,
                "quantity": 1,
                "mode": "add",
            },
        )

    assert prepare_replenish_response.status_code == 400
    assert prepare_replenish_response.json()["detail"] == "Operator replenish blocked: one or more cells are open"
    assert replenish_response.status_code == 400
    assert replenish_response.json()["detail"] == "Operator replenish blocked: one or more cells are open"
    assert prepare_remove_response.status_code == 400
    assert prepare_remove_response.json()["detail"] == "Operator removal blocked: one or more cells are open"
    assert remove_response.status_code == 400
    assert remove_response.json()["detail"] == "Operator removal blocked: one or more cells are open"
    assert refill_response.status_code == 400
    assert refill_response.json()["detail"] == "Refill blocked: one or more cells are open"


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

    with app.state.session_factory() as session:
        item = session.execute(select(Item).where(Item.sku == "nomenclature-1")).scalar_one()

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
    assert item.name == "Test Item Updated"
    assert item.status is ItemStatus.ACTIVE


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
    assert "loadUserItemsForResolvedUser" in user_js.text
    assert "USER_DISPENSE_OPTIONS_ENDPOINT" in user_js.text
    assert 'window.fetch(USER_DISPENSE_SUBMIT_ENDPOINT' in user_js.text
    assert "item-1" not in user_js.text
    assert "РџРµСЂС‡Р°С‚РєРё Р·Р°С‰РёС‚РЅС‹Рµ" not in user_js.text
    assert "loadReplenishItems" in operator_js.text
    assert 'fetch(TOUCH_NOMENCLATURE_ENDPOINT' in operator_js.text
    assert "refreshBoardState" in operator_js.text
    assert "prepareQuarterAccess" in operator_js.text
    assert "submitReplenish" in operator_js.text
    assert "submitRemove" in operator_js.text
    assert "item-01" not in operator_js.text
    assert "Р’РѕРґР° РЅРµРіР°Р·РёСЂРѕРІР°РЅРЅР°СЏ 0,5 Р»" not in operator_js.text


def test_operator_board_endpoint_returns_real_fill_state(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_board.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        response = client.get("/operator/board")

    assert response.status_code == 200
    cells = {cell["cell_number"]: cell for cell in response.json()["cells"]}
    assert cells[1]["slot_id"] == ids.slot_one_id
    assert cells[1]["filled"] is True
    assert cells[2]["slot_id"] == ids.slot_two_id
    assert cells[2]["filled"] is False
    assert cells[361]["slot_id"] == ids.slot_three_id
    assert cells[361]["filled"] is True


def test_operator_replenish_endpoint_writes_real_inventory_operations_and_events(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_replenish.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/replenish",
            json={
                "operator_user_id": ids.operator_user_id,
                "nomenclature_id": ids.nomenclature_id,
                "slot_ids": [ids.slot_two_id],
            },
        )

    assert response.status_code == 200
    assert response.json()["action"] == "replenish"
    assert response.json()["cell_numbers"] == [2]

    with app.state.session_factory() as session:
        replenished_balance = session.query(InventoryBalance).filter_by(slot_id=ids.slot_two_id, item_id=ids.item_id).one()
        operation = session.query(Operation).filter_by(slot_id=ids.slot_two_id, operation_type=OperationType.INVENTORY_ADJUSTMENT).one()
        history = session.query(OperationStateHistory).filter_by(operation_id=operation.id).one()
        transaction = session.query(InventoryTransaction).filter_by(operation_id=operation.id).one()
        event = session.query(EventLog).filter_by(operation_id=operation.id).one()
        binding = session.query(SlotItemBinding).filter_by(slot_id=ids.slot_two_id, item_id=ids.item_id, binding_type=BindingType.PRIMARY).one()

    assert replenished_balance.quantity == 1
    assert operation.user_id == ids.operator_user_id
    assert operation.item_id == ids.item_id
    assert operation.operation_state == OperationState.COMPLETED
    assert history.state == OperationState.COMPLETED
    assert transaction.quantity_before == 0
    assert transaction.quantity_after == 1
    assert transaction.quantity_delta == 1
    assert event.event_type == "operator_inventory_replenish"
    assert binding.is_active is True


def test_operator_prepare_replenish_endpoint_positions_drum_to_fixed_quarter_access_sector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drum_controller = MockDrumAdapter(initial_position=0)
    lock_controller = MockLockAdapter(lock_states={(0, 1): LockState.LOCKED, (0, 2): LockState.LOCKED})
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=MockRfidAdapter(),
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=MockRfidAdapter(),
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_operator_replenish_positioning.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/operator/inventory/replenish/prepare",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_two_id],
            },
        )

    assert response.status_code == 200
    assert hardware_bundle.facade.get_drum_position().position == 26


def test_operator_replenish_endpoint_persists_without_repositioning_drum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drum_controller = MockDrumAdapter(initial_position=31)
    lock_controller = MockLockAdapter(lock_states={(0, 1): LockState.LOCKED, (0, 2): LockState.LOCKED})
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=MockRfidAdapter(),
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=MockRfidAdapter(),
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_operator_replenish_no_reposition.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/replenish",
            json={
                "operator_user_id": ids.operator_user_id,
                "nomenclature_id": ids.nomenclature_id,
                "slot_ids": [ids.slot_two_id],
            },
        )

    assert response.status_code == 200
    assert hardware_bundle.facade.get_drum_position().position == 31


def test_operator_replenish_endpoint_prefers_real_inventory_item_for_same_name_nomenclature(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_replenish_real_item.sqlite3"))

    with app.state.session_factory() as session:
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        session.add(operator_role)
        session.flush()

        operator = User(
            role_id=operator_role.id,
            user_code="operator-1",
            full_name="Operator One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
            is_active=True,
        )
        wrong_item = Item(
            item_group_id=None,
            sku="operator-item-wrong",
            name="Operator Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        real_item = Item(
            item_group_id=None,
            sku="operator-item-real",
            name="Operator Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        nomenclature = NomenclatureEntry(
            name="Operator Item One",
            normalized_name="operator item one",
            is_active=True,
        )
        session.add_all((operator, wrong_item, real_item, nomenclature))
        session.flush()

        slot_one = Slot(
            code="slot-p00-l01",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=0,
            lock_number=1,
            capacity=1,
            status=SlotStatus.ACTIVE,
        )
        slot_two = Slot(
            code="slot-p00-l02",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=0,
            lock_number=2,
            capacity=1,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((slot_one, slot_two))
        session.flush()

        session.add(
            SlotItemBinding(
                slot_id=slot_one.id,
                item_id=real_item.id,
                binding_type=BindingType.PRIMARY,
                is_active=True,
                valid_from=None,
                valid_to=None,
            )
        )
        session.add(InventoryBalance(slot_id=slot_one.id, item_id=real_item.id, quantity=1))
        session.commit()

        operator_user_id = operator.id
        nomenclature_id = nomenclature.id
        slot_two_id = slot_two.id
        real_item_id = real_item.id
        wrong_item_id = wrong_item.id

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/replenish",
            json={
                "operator_user_id": operator_user_id,
                "nomenclature_id": nomenclature_id,
                "slot_ids": [slot_two_id],
            },
        )

    assert response.status_code == 200
    assert response.json()["item_id"] == real_item_id

    with app.state.session_factory() as session:
        real_balance = session.query(InventoryBalance).filter_by(slot_id=slot_two_id, item_id=real_item_id).one()
        wrong_balance = session.query(InventoryBalance).filter_by(slot_id=slot_two_id, item_id=wrong_item_id).one_or_none()
        binding = session.query(SlotItemBinding).filter_by(slot_id=slot_two_id, item_id=real_item_id, binding_type=BindingType.PRIMARY).one()

    assert real_balance.quantity == 1
    assert wrong_balance is None
    assert binding.is_active is True


def test_operator_replenish_endpoint_uses_machine_linked_item_for_user_availability(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_replenish_user_availability.sqlite3"))

    with app.state.session_factory() as session:
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        user_role = Role(code=RoleCode.USER, name="User")
        session.add_all((operator_role, user_role))
        session.flush()

        operator = User(
            role_id=operator_role.id,
            user_code="operator-1",
            full_name="Operator One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
            is_active=True,
        )
        user = User(
            role_id=user_role.id,
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
            is_active=True,
        )
        wrong_item = Item(
            item_group_id=None,
            sku="operator-item-wrong",
            name="Operator Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        real_item = Item(
            item_group_id=None,
            sku="operator-item-real",
            name="Operator Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        nomenclature = NomenclatureEntry(
            name="Operator Item One",
            normalized_name="operator item one",
            is_active=True,
        )
        session.add_all((operator, user, wrong_item, real_item, nomenclature))
        session.flush()

        slot_one = Slot(
            code="slot-p00-l01",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=0,
            lock_number=1,
            capacity=1,
            status=SlotStatus.ACTIVE,
        )
        slot_two = Slot(
            code="slot-p00-l02",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=0,
            lock_number=2,
            capacity=1,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((slot_one, slot_two))
        session.flush()

        session.add(
            SlotItemBinding(
                slot_id=slot_one.id,
                item_id=real_item.id,
                binding_type=BindingType.PRIMARY,
                is_active=True,
                valid_from=None,
                valid_to=None,
            )
        )
        session.add(InventoryBalance(slot_id=slot_one.id, item_id=real_item.id, quantity=1))
        session.commit()

        operator_user_id = operator.id
        user_id = user.id
        nomenclature_id = nomenclature.id
        slot_two_id = slot_two.id
        real_item_id = real_item.id
        wrong_item_id = wrong_item.id

    with TestClient(app) as client:
        replenish_response = client.post(
            "/operator/inventory/replenish",
            json={
                "operator_user_id": operator_user_id,
                "nomenclature_id": nomenclature_id,
                "slot_ids": [slot_two_id],
            },
        )
        user_options_response = client.get(
            f"/user/dispense-options?user_id={user_id}",
        )

    assert replenish_response.status_code == 200
    assert replenish_response.json()["item_id"] == real_item_id
    assert user_options_response.status_code == 200
    assert user_options_response.json()["restriction_blocked"] is False

    options = {
        option["item_id"]: option
        for option in user_options_response.json()["options"]
    }
    assert real_item_id in options
    assert wrong_item_id not in options
    assert options[real_item_id]["total_quantity"] == 2


def test_operator_replenish_endpoint_rejects_ambiguous_same_name_machine_items(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_replenish_ambiguous.sqlite3"))

    with app.state.session_factory() as session:
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        session.add(operator_role)
        session.flush()

        operator = User(
            role_id=operator_role.id,
            user_code="operator-1",
            full_name="Operator One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
            is_active=True,
        )
        item_one = Item(
            item_group_id=None,
            sku="operator-item-1",
            name="Operator Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        item_two = Item(
            item_group_id=None,
            sku="operator-item-2",
            name="Operator Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        nomenclature = NomenclatureEntry(
            name="Operator Item One",
            normalized_name="operator item one",
            is_active=True,
        )
        session.add_all((operator, item_one, item_two, nomenclature))
        session.flush()

        slot_one = Slot(
            code="slot-p00-l01",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=0,
            lock_number=1,
            capacity=1,
            status=SlotStatus.ACTIVE,
        )
        slot_two = Slot(
            code="slot-p00-l02",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=0,
            lock_number=2,
            capacity=1,
            status=SlotStatus.ACTIVE,
        )
        slot_three = Slot(
            code="slot-p00-l03",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=0,
            lock_number=3,
            capacity=1,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((slot_one, slot_two, slot_three))
        session.flush()

        session.add_all(
            (
                SlotItemBinding(
                    slot_id=slot_one.id,
                    item_id=item_one.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
                SlotItemBinding(
                    slot_id=slot_three.id,
                    item_id=item_two.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
                InventoryBalance(slot_id=slot_one.id, item_id=item_one.id, quantity=1),
                InventoryBalance(slot_id=slot_three.id, item_id=item_two.id, quantity=1),
            )
        )
        session.commit()

        operator_user_id = operator.id
        nomenclature_id = nomenclature.id
        slot_two_id = slot_two.id

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/replenish",
            json={
                "operator_user_id": operator_user_id,
                "nomenclature_id": nomenclature_id,
                "slot_ids": [slot_two_id],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Ambiguous inventory item mapping for nomenclature 'Operator Item One'"


def test_operator_remove_endpoint_rejects_mixed_invalid_batch_without_partial_changes(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_remove_validation.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/remove",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_one_id, ids.slot_two_id],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Removal rejected: selected slots are already empty: 2"

    with app.state.session_factory() as session:
        slot_one_balance = session.query(InventoryBalance).filter_by(slot_id=ids.slot_one_id, item_id=ids.item_id).one()
        operations = session.query(Operation).filter_by(operation_type=OperationType.INVENTORY_ADJUSTMENT).all()
        transactions = session.query(InventoryTransaction).all()
        events = session.query(EventLog).all()

    assert slot_one_balance.quantity == 2
    assert operations == []
    assert transactions == []
    assert events == []


def test_operator_remove_endpoint_clears_filled_slot_and_records_inventory_changes(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_operator_remove.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/remove",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_one_id],
            },
        )

    assert response.status_code == 200
    assert response.json()["action"] == "remove"
    assert response.json()["cell_numbers"] == [1]

    with app.state.session_factory() as session:
        slot_one_balance = session.query(InventoryBalance).filter_by(slot_id=ids.slot_one_id, item_id=ids.item_id).one()
        operation = session.query(Operation).filter_by(slot_id=ids.slot_one_id, operation_type=OperationType.INVENTORY_ADJUSTMENT).one()
        transaction = session.query(InventoryTransaction).filter_by(operation_id=operation.id).one()
        event = session.query(EventLog).filter_by(operation_id=operation.id).one()

    assert slot_one_balance.quantity == 0
    assert transaction.quantity_before == 2
    assert transaction.quantity_after == 0
    assert transaction.quantity_delta == -2
    assert event.event_type == "operator_inventory_remove"


def test_operator_prepare_remove_endpoint_positions_drum_to_fixed_quarter_access_sector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drum_controller = MockDrumAdapter(initial_position=0)
    lock_controller = MockLockAdapter(lock_states={(0, 1): LockState.LOCKED, (0, 2): LockState.LOCKED})
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=MockRfidAdapter(),
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=MockRfidAdapter(),
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_operator_remove_positioning.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/remove/prepare",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_three_id],
            },
        )

    assert response.status_code == 200
    assert hardware_bundle.facade.get_drum_position().position == 2


def test_operator_remove_endpoint_persists_without_repositioning_drum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drum_controller = MockDrumAdapter(initial_position=23)
    lock_controller = MockLockAdapter(lock_states={(0, 1): LockState.LOCKED, (0, 2): LockState.LOCKED})
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=MockRfidAdapter(),
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=MockRfidAdapter(),
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_operator_remove_no_reposition.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operator/inventory/remove",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_three_id],
            },
        )

    assert response.status_code == 200
    assert hardware_bundle.facade.get_drum_position().position == 23


def test_operator_prepare_replenish_returns_hardware_failure_without_inventory_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drum_controller = MockDrumAdapter(move_mode=MockHardwareMode.TIMEOUT)
    lock_controller = MockLockAdapter(lock_states={(0, 1): LockState.LOCKED, (0, 2): LockState.LOCKED})
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=MockRfidAdapter(),
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=MockRfidAdapter(),
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)
    app = create_app(_settings(tmp_path, "api_operator_replenish_hardware_failure.sqlite3"))
    ids = _seed_operator_touch_domain(app)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/operator/inventory/replenish/prepare",
            json={
                "operator_user_id": ids.operator_user_id,
                "slot_ids": [ids.slot_two_id],
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Drum controller timed out"

    with app.state.session_factory() as session:
        balance = session.query(InventoryBalance).filter_by(slot_id=ids.slot_two_id, item_id=ids.item_id).one_or_none()
        operations = session.query(Operation).filter_by(slot_id=ids.slot_two_id).all()
        transactions = session.query(InventoryTransaction).filter_by(slot_id=ids.slot_two_id).all()
        events = session.query(EventLog).filter_by(slot_id=ids.slot_two_id).all()

    assert balance is None
    assert operations == []
    assert transactions == []
    assert events == []


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
                "quantity_delta": None,
                "operation_state": "completed",
                "user_code": "operator-1",
                "user_full_name": "Operator One",
                "item_name": "Item One",
                "quantity": 5,
                "slot_code": "slot-1",
                "cell_number": 436,
            },
            {
                "operation_id": 1,
                "started_at": "2026-04-13T09:00:00",
                "operation_type": "dispense",
                "quantity_delta": None,
                "operation_state": "completed",
                "user_code": "user-1",
                "user_full_name": "User One",
                "item_name": "Item One",
                "quantity": 1,
                "slot_code": "slot-1",
                "cell_number": 436,
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
                "quantity_delta": None,
                "operation_state": "recovery_required",
                "user_code": "operator-1",
                "user_full_name": "Operator One",
                "item_name": "Item One",
                "quantity": 3,
                "slot_code": "slot-1",
                "cell_number": 436,
            },
            {
                "operation_id": 2,
                "started_at": "2026-04-13T10:00:00",
                "operation_type": "dispense",
                "quantity_delta": None,
                "operation_state": "failed",
                "user_code": "user-1",
                "user_full_name": "User One",
                "item_name": "Item One",
                "quantity": 2,
                "slot_code": "slot-1",
                "cell_number": 436,
            },
        ]
    }


def test_admin_recent_operations_endpoint_includes_inventory_adjustment_quantity_delta(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_recent_inventory_adjustment.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with app.state.session_factory() as session:
        operation = Operation(
            session_id=None,
            operation_type=OperationType.INVENTORY_ADJUSTMENT,
            operation_state=OperationState.COMPLETED,
            user_id=2,
            item_id=1,
            slot_id=1,
            qty_requested=2,
            qty_confirmed=2,
            result=None,
            error_code=None,
            error_message=None,
            hardware_context_json={},
            business_context_json={},
            started_at=datetime(2026, 4, 13, 12, 0, 0),
            finished_at=datetime(2026, 4, 13, 12, 1, 0),
        )
        session.add(operation)
        session.flush()
        session.add(
            InventoryTransaction(
                slot_id=1,
                item_id=1,
                operation_id=operation.id,
                session_id=None,
                transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                quantity_delta=-2,
                quantity_before=2,
                quantity_after=0,
                comment=None,
                created_at=datetime(2026, 4, 13, 12, 0, 30),
            )
        )
        session.commit()

    with TestClient(app) as client:
        response = client.get("/admin/operations/recent")

    assert response.status_code == 200
    assert response.json() == {
        "operations": [
            {
                "operation_id": 1,
                "started_at": "2026-04-13T12:00:00",
                "operation_type": "inventory_adjustment",
                "quantity_delta": -2,
                "operation_state": "completed",
                "user_code": "operator-1",
                "user_full_name": "Operator One",
                "item_name": "Item One",
                "quantity": 2,
                "slot_code": "slot-1",
                "cell_number": 436,
            }
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
                    operation_type=OperationType.INVENTORY_ADJUSTMENT,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=1,
                    slot_id=1,
                    qty_requested=3,
                    qty_confirmed=3,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 14, 8, 0, 0),
                    finished_at=datetime(2026, 4, 14, 8, 5, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.INVENTORY_ADJUSTMENT,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=1,
                    slot_id=1,
                    qty_requested=2,
                    qty_confirmed=2,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 14, 12, 0, 0),
                    finished_at=datetime(2026, 4, 14, 12, 5, 0),
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
        session.flush()
        session.add_all(
            [
                InventoryTransaction(
                    slot_id=1,
                    item_id=1,
                    operation_id=3,
                    session_id=None,
                    transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                    quantity_delta=3,
                    quantity_before=2,
                    quantity_after=5,
                    comment=None,
                    created_at=datetime(2026, 4, 14, 8, 0, 30),
                ),
                InventoryTransaction(
                    slot_id=1,
                    item_id=1,
                    operation_id=4,
                    session_id=None,
                    transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                    quantity_delta=-2,
                    quantity_before=5,
                    quantity_after=3,
                    comment=None,
                    created_at=datetime(2026, 4, 14, 12, 0, 30),
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
            "operation_id,started_at,finished_at,operation_type,operation_state,user_code,user_full_name,item_name,cell_number,error_code,error_message",
            "2,2026-04-14T00:00:00,2026-04-14T00:01:00,\u0412\u043e\u0437\u0432\u0440\u0430\u0442,\u041e\u0448\u0438\u0431\u043a\u0430,operator-1,Operator One,Item One,436,lock_timeout,Door lock timeout",
            "3,2026-04-14T08:00:00,2026-04-14T08:05:00,\u041f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435,\u0423\u0441\u043f\u0435\u0448\u043d\u043e,operator-1,Operator One,Item One,436,,",
            "4,2026-04-14T12:00:00,2026-04-14T12:05:00,\u0418\u0437\u044a\u044f\u0442\u0438\u0435,\u0423\u0441\u043f\u0435\u0448\u043d\u043e,operator-1,Operator One,Item One,436,,",
            "5,2026-04-14T23:59:59,2026-04-15T00:05:00,\u041f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435,\u0423\u0441\u043f\u0435\u0448\u043d\u043e,operator-1,Operator One,Item One,436,,",
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
        user.full_name = "РРІР°РЅ РџРµС‚СЂРѕРІ"
        session.commit()

    with TestClient(app) as client:
        response = client.get("/admin/users/export")

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    exported_csv = response.content.decode("utf-8-sig")
    assert exported_csv.splitlines()[0] == "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy"
    assert "user-1,РРІР°РЅ РџРµС‚СЂРѕРІ,user,000FE2767C0045,unlimited" in exported_csv


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


def test_admin_create_user_uses_manual_admin_form_payload(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_admin_create_user.sqlite3"))
    _seed_base_domain(app)
    _seed_unassigned_user(app)

    with app.state.session_factory() as session:
        session.add(Role(code=RoleCode.ADMIN, name="Admin"))
        session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/admin/users",
            json={
                "user_code": "admin-1",
                "full_name": "Admin One",
                "role_code": "admin",
                "rfid_uid": "aa bb-11 22",
                "dispense_restriction_policy": "unlimited",
                "is_active": False,
            },
        )
        list_response = client.get("/admin/users")

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "user_id": 3,
            "user_code": "admin-1",
            "full_name": "Admin One",
            "status": "inactive",
            "is_active": False,
            "role_code": "admin",
            "rfid_uid": "AABB1122",
            "dispense_restriction_policy": "unlimited",
        }
    }
    assert list_response.status_code == 200
    assert list_response.json()["users"][-1] == response.json()["user"]


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
                "quantity_delta": None,
                "operation_state": "completed",
                "user_code": "user-1",
                "user_full_name": "User One",
                "item_name": "Item One",
                "quantity": 1,
                "slot_code": "slot-1",
                "cell_number": 436,
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


def _open_door_hardware_bundle(*, board_address: int, lock_number: int) -> HardwareBundle:
    return HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=MockDrumAdapter(),
        lock_controller=MockLockAdapter(lock_states={(board_address, lock_number): LockState.OPEN}),
        rfid_reader=MockRfidAdapter(),
        facade=HardwareFacade(
            drum_controller=MockDrumAdapter(),
            lock_controller=MockLockAdapter(lock_states={(board_address, lock_number): LockState.OPEN}),
            rfid_reader=MockRfidAdapter(),
        ),
    )


class _OperatorTouchSeedIds:
    def __init__(
        self,
        *,
        operator_user_id: int,
        item_id: int,
        nomenclature_id: int,
        slot_one_id: int,
        slot_two_id: int,
        slot_three_id: int,
    ) -> None:
        self.operator_user_id = operator_user_id
        self.item_id = item_id
        self.nomenclature_id = nomenclature_id
        self.slot_one_id = slot_one_id
        self.slot_two_id = slot_two_id
        self.slot_three_id = slot_three_id


def _seed_operator_touch_domain(app) -> _OperatorTouchSeedIds:
    with app.state.session_factory() as session:
        operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
        session.add(operator_role)
        session.flush()

        operator = User(
            role_id=operator_role.id,
            user_code="operator-1",
            full_name="Operator One",
            status=UserStatus.ACTIVE,
            dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
            is_active=True,
        )
        item = Item(
            item_group_id=None,
            sku="operator-item-1",
            name="Operator Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        nomenclature = NomenclatureEntry(
            name="Operator Item One",
            normalized_name="operator item one",
            is_active=True,
        )
        session.add_all((operator, item, nomenclature))
        session.flush()

        slot_one = session.query(Slot).filter_by(drum_position=0, lock_number=1).one_or_none()
        if slot_one is None:
            slot_one = Slot(
                code="slot-p00-l01",
                slot_type=SlotType.UNIVERSAL,
                drum_position=0,
                board_address=0,
                lock_number=1,
                capacity=1,
                status=SlotStatus.ACTIVE,
            )
            session.add(slot_one)
        slot_two = session.query(Slot).filter_by(drum_position=0, lock_number=2).one_or_none()
        if slot_two is None:
            slot_two = Slot(
                code="slot-p00-l02",
                slot_type=SlotType.UNIVERSAL,
                drum_position=0,
                board_address=0,
                lock_number=2,
                capacity=1,
                status=SlotStatus.ACTIVE,
            )
            session.add(slot_two)
        slot_three = session.query(Slot).filter_by(drum_position=8, lock_number=1).one_or_none()
        if slot_three is None:
            slot_three = Slot(
                code="slot-p08-l01",
                slot_type=SlotType.UNIVERSAL,
                drum_position=8,
                board_address=0,
                lock_number=1,
                capacity=1,
                status=SlotStatus.ACTIVE,
            )
            session.add(slot_three)
        session.flush()

        session.add_all(
            [
                SlotItemBinding(
                    slot_id=slot_one.id,
                    item_id=item.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
                SlotItemBinding(
                    slot_id=slot_three.id,
                    item_id=item.id,
                    binding_type=BindingType.PRIMARY,
                    is_active=True,
                    valid_from=None,
                    valid_to=None,
                ),
            ]
        )
        session.add_all(
            [
                InventoryBalance(slot_id=slot_one.id, item_id=item.id, quantity=2),
                InventoryBalance(slot_id=slot_three.id, item_id=item.id, quantity=1),
            ]
        )
        operator_user_id = operator.id
        item_id = item.id
        nomenclature_id = nomenclature.id
        slot_one_id = slot_one.id
        slot_two_id = slot_two.id
        slot_three_id = slot_three.id
        session.commit()

    return _OperatorTouchSeedIds(
        operator_user_id=operator_user_id,
        item_id=item_id,
        nomenclature_id=nomenclature_id,
        slot_one_id=slot_one_id,
        slot_two_id=slot_two_id,
        slot_three_id=slot_three_id,
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
        return _FakeRealDispenseTransport(
            [
                _fake_lock_board_status_response(data=bytes.fromhex("FF 7F 00")),
                _fake_lock_board_status_response(data=bytes.fromhex("FF 7F 00")),
                bytes.fromhex("02 00 00 81 10 00 03 96"),
            ]
        )
    if config.endpoint.code == "rfid-1":
        return _FakeRealDispenseTransport([b"PONG\n"])
    return _FakeRealDispenseTransport([], sequence_responses=[bytes.fromhex("21 AA AA C4"), bytes.fromhex("25 C0")])


def _fake_lock_board_status_response(*, data: bytes, board_address: int = 0, lock_number: int = 0) -> bytes:
    header = bytes((0x02, board_address, lock_number, 0x80, 0x10, len(data), 0x03))
    checksum = (sum(header) + sum(data)) & 0xFF
    return header + bytes((checksum,)) + data


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
