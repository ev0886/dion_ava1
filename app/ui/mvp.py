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
        "userDoorStatusEndpoint": "/user/door-status",
        "userDoorStatusPollIntervalMs": 300,
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
        "operatorPrepareReplenishEndpoint": "/operator/inventory/replenish/prepare",
        "operatorReplenishEndpoint": "/operator/inventory/replenish",
        "operatorPrepareRemoveEndpoint": "/operator/inventory/remove/prepare",
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
        "createUserEndpoint": "/admin/users",
        "listNomenclatureEndpoint": "/admin/nomenclature",
        "createNomenclatureEndpoint": "/admin/nomenclature",
        "updateNomenclatureEndpointBase": "/admin/nomenclature",
        "problemOperationsEndpoint": "/admin/operations/problem",
        "recentOperationsEndpoint": "/admin/operations/recent",
        "exportOperationsEndpoint": "/admin/operations/export",
        "exportBalancesEndpoint": "/admin/balances/export",
        "exportUsersEndpoint": "/admin/users/export",
        "logoutEndpoint": "/admin/auth/logout",
        "changePasswordEndpoint": "/admin/auth/password",
        "updateUserEndpointBase": "/admin/users",
        "importUsersEndpoint": "/admin/users/import",
        "importExampleCsvAssetUrl": "/ui-assets/admin-users-import-example.csv",
        "importExampleCsvText": _ADMIN_USERS_IMPORT_EXAMPLE_CSV,
        "supportedRoles": ["admin", "operator", "user"],
        "supportedPolicies": ["unlimited", "once_per_day"],
    }
    return HTMLResponse(
        template.replace(
            "__DION_ADMIN_UI_CONFIG__",
            json.dumps(ui_config, ensure_ascii=True),
        )
    )


def render_admin_login_page(settings: AppSettings) -> HTMLResponse:
    del settings
    return HTMLResponse(
        """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DION ABA1 Admin Login</title>
  <link rel="stylesheet" href="/ui-assets/admin.css">
</head>
<body>
  <main class="admin-login-shell">
    <section class="panel admin-login-panel">
      <p class="eyebrow">DION ABA1 Admin UI</p>
      <h1>Admin login</h1>
      <div class="status-panel" id="login-status" aria-live="polite">
        <strong id="login-status-title">Authentication required</strong>
        <p id="login-status-message">Enter admin credentials to continue.</p>
      </div>
      <label class="field-block" for="admin-login">
        <span class="field-label">Login</span>
        <input id="admin-login" class="inline-input" type="text" value="admin" autocomplete="username">
      </label>
      <label class="field-block" for="admin-password">
        <span class="field-label">Password</span>
        <input id="admin-password" class="inline-input" type="password" autocomplete="current-password">
      </label>
      <button id="admin-login-button" class="save-button" type="button">Login</button>
    </section>
  </main>
  <script>
    (function () {
      const loginInput = document.getElementById("admin-login");
      const passwordInput = document.getElementById("admin-password");
      const loginButton = document.getElementById("admin-login-button");
      const status = document.getElementById("login-status");
      const title = document.getElementById("login-status-title");
      const message = document.getElementById("login-status-message");

      function setStatus(kind, nextTitle, nextMessage) {
        status.className = "status-panel" + (kind ? " status-" + kind : "");
        title.textContent = nextTitle;
        message.textContent = nextMessage;
      }

      async function login() {
        loginButton.disabled = true;
        setStatus("", "Checking credentials", "Please wait.");
        try {
          const response = await fetch("/admin/auth/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({login: loginInput.value, password: passwordInput.value})
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.detail || "Login failed");
          }
          window.location.assign("/ui/admin");
        } catch (error) {
          setStatus("error", "Login failed", String(error));
        } finally {
          loginButton.disabled = false;
        }
      }

      loginButton.addEventListener("click", function () { void login(); });
      passwordInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          void login();
        }
      });
      passwordInput.focus();
    })();
  </script>
</body>
</html>"""
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
