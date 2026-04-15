from __future__ import annotations

import json
from pathlib import Path

from fastapi.responses import HTMLResponse

from app.config import AppSettings

_UI_DIR = Path(__file__).resolve().parent
_MVP_TEMPLATE_PATH = _UI_DIR / "templates" / "mvp.html"
_OPERATOR_TEMPLATE_PATH = _UI_DIR / "templates" / "operator.html"
_ADMIN_TEMPLATE_PATH = _UI_DIR / "templates" / "admin.html"


def render_user_page(settings: AppSettings) -> HTMLResponse:
    del settings
    template = _MVP_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "uiRole": "user",
        "authEndpoint": "/auth/read-and-resolve-rfid",
        "dispenseEndpoint": "/operations/dispense",
        "optionsEndpoint": "/inventory/kiosk-dispense-options",
        "autoResetTimeoutMs": 15000,
        "dispenseQuantity": 1,
    }
    return HTMLResponse(template.replace("__DION_UI_CONFIG__", json.dumps(ui_config, ensure_ascii=True)))


def render_operator_page(settings: AppSettings) -> HTMLResponse:
    del settings
    template = _OPERATOR_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "uiRole": "operator",
        "overviewEndpoint": "/inventory/replenishment-overview",
        "refillEndpoint": "/operations/refill",
        "defaultRefillMode": "add",
    }
    return HTMLResponse(template.replace("__DION_OPERATOR_UI_CONFIG__", json.dumps(ui_config, ensure_ascii=True)))


def render_admin_page(settings: AppSettings) -> HTMLResponse:
    del settings
    template = _ADMIN_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {"uiRole": "admin"}
    return HTMLResponse(template.replace("__DION_ADMIN_UI_CONFIG__", json.dumps(ui_config, ensure_ascii=True)))
