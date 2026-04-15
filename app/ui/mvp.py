from __future__ import annotations

import json
from pathlib import Path

from fastapi.responses import HTMLResponse

from app.config import AppSettings

_UI_DIR = Path(__file__).resolve().parent
_MVP_TEMPLATE_PATH = _UI_DIR / "templates" / "mvp.html"
_ADMIN_TEMPLATE_PATH = _UI_DIR / "templates" / "admin.html"
_ADMIN_USERS_IMPORT_EXAMPLE_CSV = "\n".join(
    [
        "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
        "user-1001,Ivan Petrov,user,11 22 aa bb,unlimited",
        "operator-2001,Anna Sidorova,operator,44 55 cc dd,once_per_day",
    ]
)


def render_mvp_page(settings: AppSettings) -> HTMLResponse:
    template = _MVP_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "authEndpoint": "/auth/read-and-resolve-rfid",
        "dispenseEndpoint": "/operations/dispense",
        "optionsEndpoint": "/inventory/kiosk-dispense-options",
        "usbStatusEndpoint": "/local/usb/status",
        "localUsbOperationsExportEndpoint": "/local/usb/export/operations",
        "localUsbUsersExportEndpoint": "/local/usb/export/users",
        "autoResetTimeoutMs": 15000,
        "dispenseQuantity": 1,
    }
    return HTMLResponse(
        template.replace(
            "__DION_UI_CONFIG__",
            json.dumps(ui_config, ensure_ascii=True),
        )
    )


def render_admin_page(settings: AppSettings) -> HTMLResponse:
    template = _ADMIN_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "systemStatusEndpoint": "/admin/system/status",
        "listUsersEndpoint": "/admin/users",
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
