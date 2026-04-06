from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RoleCode


class ApiModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class AuthResolveRequest(ApiModel):
    user_id: int | None = Field(
        default=None,
        description="Known user ID. Demo stand example: 3 for user-1.",
    )
    user_code: str | None = Field(
        default=None,
        description='Alternative identifier when resolving by code instead of numeric ID. Demo stand example: "user-1".',
    )
    allowed_roles: tuple[RoleCode, ...] = Field(
        default=(),
        description="Optional role filter. Leave empty to resolve any active user.",
    )


class DispenseOperationRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 3,
                "item_id": 1,
                "slot_id": 1,
                "quantity": 1,
                "session_id": None,
            }
        }
    )

    user_id: int = Field(description="End user performing the dispense. Demo stand example: 3 for user-1.")
    item_id: int = Field(description="Item to dispense. Demo stand example: 1.")
    slot_id: int = Field(description="Physical slot expected to dispense the item. Demo stand example: 1.")
    quantity: int = Field(default=1, description="Requested quantity. The tested happy path uses 1.")
    session_id: int | None = Field(
        default=None,
        description="Optional operation session. Use null for the normal happy path when no service session is active.",
    )


class ReturnOperationRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 3,
                "item_id": 1,
                "slot_id": None,
                "quantity": 1,
                "session_id": None,
            }
        }
    )

    user_id: int = Field(description="End user returning the item. Demo stand example: 3 for user-1.")
    item_id: int = Field(description="Returned item ID. Demo stand example: 1.")
    slot_id: int | None = Field(
        default=None,
        description="Optional return slot. Leave null when the backend should resolve the return-capable slot automatically.",
    )
    quantity: int = Field(default=1, description="Returned quantity. The tested happy path uses 1.")
    session_id: int | None = Field(
        default=None,
        description="Optional operation session. Use null for the normal happy path when no service session is active.",
    )


class RefillOperationRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "operator_user_id": 2,
                "item_id": 1,
                "slot_id": 1,
                "quantity": 5,
                "mode": "set",
                "session_id": None,
            }
        }
    )

    operator_user_id: int = Field(description="Operator performing the refill. Demo stand example: 2 for operator-1.")
    item_id: int = Field(description="Item being refilled. Demo stand example: 1.")
    slot_id: int = Field(description="Slot being refilled. Demo stand example: 1.")
    quantity: int = Field(description="Quantity to apply using the selected mode.")
    mode: Literal["set", "add"] = Field(
        default="set",
        description='Refill strategy: "set" replaces the quantity, "add" increments the current balance.',
    )
    session_id: int | None = Field(
        default=None,
        description="Optional service session. Use null to let the backend create or resolve the service session flow.",
    )


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


class RecoveryManualResolutionRequest(ApiModel):
    operator_user_id: int = Field(description="Operator resolving the case. Demo stand example: 2 for operator-1.")
    decision: str = Field(description='Manual resolution decision. Operator-tested example: "close_case".')
    comment: str | None = Field(
        default=None,
        description='Optional operator note recorded with the resolution. Example: "Operator verified physical state".',
    )


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
