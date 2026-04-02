from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import BindingType, ItemStatus, RoleCode, UserStatus


@dataclass(frozen=True, slots=True)
class UserRfidBindingDTO:
    card_uid: str
    is_active: bool
    issued_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class UserSummaryDTO:
    user_id: int
    user_code: str
    full_name: str
    role_id: int
    role_code: RoleCode | None
    role_name: str | None
    status: UserStatus
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class UserDetailDTO(UserSummaryDTO):
    rfid_bindings: tuple[UserRfidBindingDTO, ...]


@dataclass(frozen=True, slots=True)
class UserListResultDTO:
    users: tuple[UserSummaryDTO, ...]


@dataclass(frozen=True, slots=True)
class ItemSlotBindingDTO:
    slot_id: int
    slot_code: str
    binding_type: BindingType
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None


@dataclass(frozen=True, slots=True)
class ItemInventorySummaryDTO:
    total_quantity: int
    slot_quantities: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ItemSummaryDTO:
    item_id: int
    item_group_id: int | None
    item_group_code: str | None
    item_group_name: str | None
    sku: str
    name: str
    description: str | None
    unit: str
    return_allowed: bool
    min_level: int
    status: ItemStatus


@dataclass(frozen=True, slots=True)
class ItemDetailDTO(ItemSummaryDTO):
    active_slot_bindings: tuple[ItemSlotBindingDTO, ...]
    inventory_summary: ItemInventorySummaryDTO


@dataclass(frozen=True, slots=True)
class ItemListResultDTO:
    items: tuple[ItemSummaryDTO, ...]


@dataclass(frozen=True, slots=True)
class PermissionDetailDTO:
    permission_id: int
    user_id: int
    item_id: int | None
    item_group_id: int | None
    target_type: str
    target_code: str | None
    target_name: str | None
    can_dispense: bool
    can_return: bool
    valid_from: datetime | None
    valid_to: datetime | None
    is_active: bool
    comment: str | None


@dataclass(frozen=True, slots=True)
class PermissionListResultDTO:
    user_id: int
    permissions: tuple[PermissionDetailDTO, ...]
