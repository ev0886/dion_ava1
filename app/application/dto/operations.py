from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.domain.enums import OperationState, OperationType, SessionStatus, SessionType

RefillMode = Literal["set", "add"]


@dataclass(frozen=True, slots=True)
class CreateOperationSessionCommand:
    session_type: SessionType
    started_by_user_id: int | None = None
    comment: str | None = None
    context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationSessionDTO:
    session_id: int | None
    session_type: SessionType
    status: SessionStatus
    started_by_user_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    comment: str | None
    context: dict[str, object]


@dataclass(frozen=True, slots=True)
class CreateOperationCommand:
    operation_type: OperationType
    session_id: int | None = None
    user_id: int | None = None
    item_id: int | None = None
    slot_id: int | None = None
    qty_requested: int = 0
    operation_state: OperationState = OperationState.CREATED
    business_context: dict[str, object] = field(default_factory=dict)
    hardware_context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DispenseRequest:
    user_id: int
    item_id: int
    slot_id: int | None = None
    quantity: int = 1
    session_id: int | None = None


@dataclass(frozen=True, slots=True)
class ReturnRequest:
    user_id: int
    item_id: int
    slot_id: int | None = None
    quantity: int = 1
    session_id: int | None = None


@dataclass(frozen=True, slots=True)
class RefillRequest:
    operator_user_id: int
    item_id: int
    slot_id: int
    quantity: int
    mode: RefillMode = "set"
    session_id: int | None = None


@dataclass(frozen=True, slots=True)
class OperationDTO:
    operation_id: int | None
    session_id: int | None
    operation_type: OperationType
    operation_state: OperationState
    user_id: int | None
    item_id: int | None
    slot_id: int | None
    qty_requested: int
    qty_confirmed: int | None
    result: str | None
    error_code: str | None
    error_message: str | None
    hardware_context: dict[str, object]
    business_context: dict[str, object]
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class OperationValidationResult:
    operation_type: OperationType
    valid: bool
    messages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationContextDTO:
    operation_type: OperationType
    user_id: int | None
    item_id: int | None
    slot_id: int | None
    session_id: int | None
    operation_state: OperationState
    business_context: dict[str, object]
    hardware_context: dict[str, object]


@dataclass(frozen=True, slots=True)
class TransitionCheckResult:
    operation_type: OperationType
    current_state: OperationState
    target_state: OperationState
    allowed: bool
