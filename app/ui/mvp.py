from __future__ import annotations

import json
from pathlib import Path

from fastapi.responses import HTMLResponse

from app.config import AppSettings

_UI_DIR = Path(__file__).resolve().parent
_MVP_TEMPLATE_PATH = _UI_DIR / "templates" / "mvp.html"


def render_mvp_page(settings: AppSettings) -> HTMLResponse:
    template = _MVP_TEMPLATE_PATH.read_text(encoding="utf-8")
    ui_config = {
        "authEndpoint": "/auth/read-and-resolve-rfid",
        "dispenseEndpoint": "/operations/dispense",
        "optionsEndpoint": "/inventory/available-dispense-options",
        "autoResetTimeoutMs": 15000,
        "dispenseQuantity": 1,
    }
    return HTMLResponse(
        template.replace(
            "__DION_UI_CONFIG__",
            json.dumps(ui_config, ensure_ascii=True),
        )
    )
