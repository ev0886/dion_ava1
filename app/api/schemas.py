from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ItemStatus, RoleCode, UserStatus


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


class UserCreateRequest(ApiModel):
    user_code: str
    full_name: str
    role_id: int
    actor_user_id: int | None = None
    comment: str | None = None


class UserUpdateRequest(ApiModel):
    user_code: str | None = None
    full_name: str | None = None
    role_id: int | None = None
    is_active: bool | None = None
    actor_user_id: int | None = None
    comment: str | None = None


class ItemCreateRequest(ApiModel):
    sku: str
    name: str
    unit: str
    item_group_id: int | None = None
    description: str | None = None
    return_allowed: bool = False
    min_level: int = 0
    actor_user_id: int | None = None
    comment: str | None = None


class ItemUpdateRequest(ApiModel):
    sku: str | None = None
    name: str | None = None
    unit: str | None = None
    item_group_id: int | None = None
    description: str | None = None
    return_allowed: bool | None = None
    min_level: int | None = None
    is_active: bool | None = None
    actor_user_id: int | None = None
    comment: str | None = None


class PermissionAssignRequest(ApiModel):
    user_id: int
    item_id: int | None = None
    item_group_id: int | None = None
    can_dispense: bool = False
    can_return: bool = False
    actor_user_id: int | None = None
    comment: str | None = None


class PermissionRevokeRequest(ApiModel):
    actor_user_id: int | None = None
    comment: str | None = None


class UserListQuery(ApiModel):
    role_id: int | None = None
    status: UserStatus | None = None
    is_active: bool | None = None
    search: str | None = None


class ItemListQuery(ApiModel):
    item_group_id: int | None = None
    status: ItemStatus | None = None
    search: str | None = None


class ErrorResponse(ApiModel):
    error: str
    detail: str


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
