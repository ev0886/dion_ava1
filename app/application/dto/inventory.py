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
class AvailableDispenseOptionDTO:
    slot_id: int
    item_id: int
    quantity: int
    updated_at: datetime | None
    slot_code: str
    drum_position: int
    board_address: int
    lock_number: int
    item_sku: str
    item_name: str
    item_unit: str


@dataclass(frozen=True, slots=True)
class AvailableDispenseOptionsResult:
    options: tuple[AvailableDispenseOptionDTO, ...]


@dataclass(frozen=True, slots=True)
class KioskDispenseOptionDTO:
    item_id: int
    item_name: str
    item_unit: str
    total_quantity: int


@dataclass(frozen=True, slots=True)
class KioskDispenseOptionsResult:
    options: tuple[KioskDispenseOptionDTO, ...]


@dataclass(frozen=True, slots=True)
class UserDispenseOptionDTO:
    item_id: int
    item_name: str
    item_unit: str
    total_quantity: int


@dataclass(frozen=True, slots=True)
class UserDispenseOptionsResult:
    options: tuple[UserDispenseOptionDTO, ...]
    restriction_blocked: bool = False
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperatorBoardCellDTO:
    slot_id: int
    cell_number: int
    sector_number: int
    quarter_number: int
    drum_position: int
    lock_number: int
    filled: bool


@dataclass(frozen=True, slots=True)
class OperatorBoardStateResult:
    cells: tuple[OperatorBoardCellDTO, ...]


@dataclass(frozen=True, slots=True)
class OperatorInventoryActionResult:
    action: str
    operator_user_id: int
    item_id: int | None
    item_name: str | None
    nomenclature_id: int | None
    slot_ids: tuple[int, ...]
    cell_numbers: tuple[int, ...]
    operation_ids: tuple[int, ...]
