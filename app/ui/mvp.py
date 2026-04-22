from __future__ import annotations

import json
from pathlib import Path

from fastapi.responses import HTMLResponse

from app.config import AppSettings

_UI_DIR = Path(__file__).resolve().parent
_MVP_TEMPLATE_PATH = _UI_DIR / "templates" / "mvp.html"
_OPERATOR_TEMPLATE_PATH = _UI_DIR / "templates" / "operator.html"
_ADMIN_TEMPLATE_PATH = _UI_DIR / "templates" / "admin.html"
_ADMIN_TOUCH_TEMPLATE_PATH = _UI_DIR / "templates" / "admin_touch.html"
_ADMIN_TOUCH_CSS_PATH = _UI_DIR / "static" / "admin-touch.css"
_ADMIN_TOUCH_JS_PATH = _UI_DIR / "static" / "admin-touch.js"
_ADMIN_USERS_IMPORT_EXAMPLE_CSV = "\n".join(
    [
        "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
        "user-1001,Ivan Petrov,user,11 22 aa bb,unlimited",
        "operator-2001,Anna Sidorova,operator,44 55 cc dd,once_per_day",
    ]
)


def _build_admin_touch_asset_version() -> str:
    latest_mtime_ns = max(
        _ADMIN_TOUCH_TEMPLATE_PATH.stat().st_mtime_ns,
        _ADMIN_TOUCH_CSS_PATH.stat().st_mtime_ns,
        _ADMIN_TOUCH_JS_PATH.stat().st_mtime_ns,
    )
    return str(latest_mtime_ns)


def render_user_page(settings: AppSettings) -> HTMLResponse:
    template = _MVP_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "uiRole": "user",
        "uiFlowMode": "rfid-auth-shell",
        "uiIdleTimeoutMs": 30000,
        "authErrorReturnTimeoutMs": 2400,
        "authSuccessRouteDelayMs": 1000,
        "presenceCountdownSeconds": 30,
        "authReadAndResolveRfidEndpoint": "/auth/read-and-resolve-rfid",
        "touchRoleRoutes": {
            "user": "/ui/user",
            "operator": "/ui/operator",
            "admin": "/ui/admin-touch",
        },
        "touchAuthStorageKey": "dion.touchAuthContext",
        "userDispenseOptionsEndpoint": "/user/dispense-options",
        "userDispenseSubmitEndpoint": "/user/dispense",
        "userOpenDoorStatusEndpoint": "/user/open-door-status",
        "userDispenseStatusEndpoint": "/user/dispense-status",
        "emptyNomenclatureMessage": "Номенклатура не настроена",
    }
    return HTMLResponse(
        template.replace(
            "__DION_UI_CONFIG__",
            json.dumps(ui_config, ensure_ascii=True),
        )
    )


def render_operator_page(settings: AppSettings) -> HTMLResponse:
    template = _OPERATOR_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "uiRole": "operator",
        "refillWorkflowStatus": "real-db-no-hardware",
        "touchAuthStorageKey": "dion.touchAuthContext",
        "listTouchNomenclatureEndpoint": "/touch/nomenclature",
        "operatorBoardStateEndpoint": "/operator/board",
        "operatorReplenishEndpoint": "/operator/inventory/replenish",
        "operatorRemoveEndpoint": "/operator/inventory/remove",
        "emptyNomenclatureMessage": "Номенклатура не настроена",
    }
    return HTMLResponse(
        template.replace(
            "__DION_OPERATOR_UI_CONFIG__",
            json.dumps(ui_config, ensure_ascii=True),
        )
    )


def render_admin_page(settings: AppSettings) -> HTMLResponse:
    template = _ADMIN_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "uiRole": "admin",
        "systemStatusEndpoint": "/admin/system/status",
        "listUsersEndpoint": "/admin/users",
        "listNomenclatureEndpoint": "/admin/nomenclature",
        "createNomenclatureEndpoint": "/admin/nomenclature",
        "updateNomenclatureEndpointBase": "/admin/nomenclature",
        "problemOperationsEndpoint": "/admin/operations/problem",
        "recentOperationsEndpoint": "/admin/operations/recent",
        "exportOperationsEndpoint": "/admin/operations/export",
        "exportUsersEndpoint": "/admin/users/export",
        "updateUserEndpointBase": "/admin/users",
        "importUsersEndpoint": "/admin/users/import",
        "importExampleCsvAssetUrl": "/ui-assets/admin-users-import-example.csv",
        "importExampleCsvText": _ADMIN_USERS_IMPORT_EXAMPLE_CSV,
        "supportedPolicies": ["unlimited", "once_per_day"],
    }
    return HTMLResponse(
        template.replace(
            "__DION_ADMIN_UI_CONFIG__",
            json.dumps(ui_config, ensure_ascii=True),
        )
    )


def render_admin_touch_page(settings: AppSettings) -> HTMLResponse:
    template = _ADMIN_TOUCH_TEMPLATE_PATH.read_text(encoding="utf-8")
    asset_version = _build_admin_touch_asset_version()
    ui_config = {
        "uiRole": "admin-touch",
        "availableActions": [
            "Экспорт остатков",
            "Экспорт операций",
            "Экспорт пользователей",
            "Импорт пользователей",
        ],
        "operationsDefaultDateFrom": "01.04.2026",
        "operationsDefaultDateTo": "21.04.2026",
        "progressAdvanceDelayMs": 1800,
        "successReturnDelayMs": 2400,
        "uiIdleTimeoutMs": 30000,
        "presenceCountdownSeconds": 30,
        "startScreenRoute": "/ui/user",
        "exportBalancesEndpoint": "/local/usb/export/balances",
        "exportOperationsEndpoint": "/local/usb/export/operations",
        "exportUsersEndpoint": "/local/usb/export/users",
        "checkImportUsersEndpoint": "/local/usb/import/users/check",
        "importUsersEndpoint": "/local/usb/import/users",
    }
    return HTMLResponse(
        template
        .replace(
            "__DION_ADMIN_TOUCH_ASSET_VERSION__",
            asset_version,
        )
        .replace(
            "__DION_ADMIN_TOUCH_UI_CONFIG__",
            json.dumps(ui_config, ensure_ascii=True),
        )
    )
