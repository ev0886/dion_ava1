from __future__ import annotations

from app.domain.enums import RoleCode

DEFAULT_SQLITE_BUSY_TIMEOUT_MS = 5_000
DEFAULT_PIN_MAX_ATTEMPTS = 5
DEFAULT_PIN_MIN_LENGTH = 4
DEFAULT_RFID_UID_FORMAT = "HEX_UPPERCASE"

DEFAULT_ROLE_NAMES: dict[RoleCode, str] = {
    RoleCode.ADMIN: "Administrator",
    RoleCode.OPERATOR: "Operator",
    RoleCode.USER: "User",
}
