from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.domain.enums import RoleCode


class ApiModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class AuthResolveRequest(ApiModel):
    user_id: int | None = None
    user_code: str | None = None
    allowed_roles: tuple[RoleCode, ...] = ()


class DispenseOperationRequest(ApiModel):
    user_id: int
    item_id: int
    slot_id: int
    quantity: int = 1
    session_id: int | None = None


class ReturnOperationRequest(ApiModel):
    user_id: int
    item_id: int
    slot_id: int | None = None
    quantity: int = 1
    session_id: int | None = None


class RefillOperationRequest(ApiModel):
    operator_user_id: int
    item_id: int
    slot_id: int
    quantity: int
    mode: Literal["set", "add"] = "set"
    session_id: int | None = None


class ServiceModeStartRequest(ApiModel):
    user_id: int
    comment: str | None = None


class ServiceModeFinishRequest(ApiModel):
    session_id: int
    user_id: int
    comment: str | None = None


class ExportCreateRequest(ApiModel):
    requested_by_user_id: int
    destination_type: str = "filesystem"
    destination_path: str = "var/exports"
    comment: str | None = None


class ErrorResponse(ApiModel):
    error: str
    detail: str
    message: str
    reason_code: str | None = None
    action: str | None = None


def to_api_payload(value: Any) -> Any:
    from dataclasses import asdict, is_dataclass
    from datetime import date, datetime
    from enum import Enum
    from pathlib import Path

    if is_dataclass(value):
        return to_api_payload(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_api_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_api_payload(item) for item in value]
    return value
