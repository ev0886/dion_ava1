from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import BindingType, InventoryTransactionType, SlotStatus, SlotType


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
    binding_id: int | None = None


@dataclass(frozen=True, slots=True)
class InventoryLookupResult:
    slot_id: int
    item_id: int
    balance: InventoryBalanceDTO | None
    bindings: tuple[SlotBindingDTO, ...]


@dataclass(frozen=True, slots=True)
class SlotDTO:
    slot_id: int
    code: str
    slot_type: SlotType
    drum_position: int
    board_address: int
    lock_number: int
    capacity: int | None
    status: SlotStatus


@dataclass(frozen=True, slots=True)
class SlotDetailDTO:
    slot: SlotDTO
    active_bindings: tuple[SlotBindingDTO, ...]
    inventory_balances: tuple[InventoryBalanceDTO, ...]


@dataclass(frozen=True, slots=True)
class InventoryAdjustmentResultDTO:
    slot_id: int
    item_id: int
    transaction_type: InventoryTransactionType
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    comment: str | None
    created_at: datetime
    balance: InventoryBalanceDTO
