from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import BindingType


@dataclass(frozen=True, slots=True)
class InventoryBalanceDTO:
    slot_id: int
    item_id: int
    quantity: int
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class SlotBindingDTO:
    slot_id: int
    item_id: int
    binding_type: BindingType
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None


@dataclass(frozen=True, slots=True)
class InventoryLookupResult:
    slot_id: int
    item_id: int
    balance: InventoryBalanceDTO | None
    bindings: tuple[SlotBindingDTO, ...]


@dataclass(frozen=True, slots=True)
class ReplenishmentOptionDTO:
    item_id: int
    item_name: str
    item_sku: str
    item_unit: str
    item_min_level: int
    slot_id: int
    slot_code: str
    slot_status: str
    slot_type: str
    drum_position: int
    board_address: int
    lock_number: int
    capacity: int | None
    binding_type: BindingType
    quantity: int
    updated_at: datetime | None
