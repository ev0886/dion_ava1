from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from app.domain.enums import (
    ItemStatus,
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)

TItem = TypeVar("TItem")


@dataclass(frozen=True, slots=True)
class Pagination:
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class PaginatedResult(Generic[TItem]):
    items: tuple[TItem, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class UserListItemDTO:
    user_id: int | None
    user_code: str
    full_name: str
    status: UserStatus
    is_active: bool
    role_code: RoleCode | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ItemListItemDTO:
    item_id: int | None
    item_group_id: int | None
    sku: str
    name: str
    unit: str
    return_allowed: bool
    min_level: int
    status: ItemStatus


@dataclass(frozen=True, slots=True)
class SlotListItemDTO:
    slot_id: int | None
    code: str
    slot_type: SlotType
    drum_position: int
    board_address: int
    lock_number: int
    capacity: int | None
    status: SlotStatus


@dataclass(frozen=True, slots=True)
class RecoveryCaseListFilters:
    status: RecoveryStatus | None = None
    classification: RecoveryClassification | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class OperationListFilters:
    operation_state: OperationState | None = None
    operation_type: OperationType | None = None
    user_id: int | None = None
    item_id: int | None = None
    slot_id: int | None = None
    session_id: int | None = None


@dataclass(frozen=True, slots=True)
class UserListFilters:
    status: UserStatus | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class ItemListFilters:
    status: ItemStatus | None = None


@dataclass(frozen=True, slots=True)
class SlotListFilters:
    status: SlotStatus | None = None
    slot_type: SlotType | None = None


@dataclass(frozen=True, slots=True)
class EventLogListItemDTO:
    event_log_id: int | None
    event_type: str
    level: str
    source: str
    operation_id: int | None
    session_id: int | None
    user_id: int | None
    slot_id: int | None
    item_id: int | None
    qty: Decimal | float | None
    result: str | None
    comment: str | None
    message: str | None
    payload: dict[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EventLogListFilters:
    event_type: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuditLogListItemDTO:
    audit_log_id: int | None
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: int | None
    reason_code: str | None
    comment: str | None
    before: dict[str, object]
    after: dict[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditLogListFilters:
    entity_type: str | None = None
    action: str | None = None
    reason_code: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
