from __future__ import annotations

from sqlalchemy import select

from app.application.dto.inventory import (
    InventoryBalanceDTO,
    InventoryLookupResult,
    ReplenishmentOptionDTO,
    SlotBindingDTO,
)
from app.application.exceptions import ValidationError
from app.domain.enums import ItemStatus, SlotStatus
from app.persistence.models import InventoryBalance, Item, Slot, SlotItemBinding
from app.persistence.repositories.inventory import InventoryRepository


class InventoryService:
    def __init__(self, inventory_repository: InventoryRepository) -> None:
        self.inventory_repository = inventory_repository

    def get_balance(self, slot_id: int, item_id: int) -> InventoryBalanceDTO | None:
        self._validate_slot_item_ids(slot_id, item_id)
        balance = self.inventory_repository.get_balance(slot_id, item_id)
        if balance is None:
            return None
        return self._to_balance_dto(balance)

    def lookup_inventory(self, slot_id: int, item_id: int) -> InventoryLookupResult:
        self._validate_slot_item_ids(slot_id, item_id)
        balance = self.inventory_repository.get_balance(slot_id, item_id)
        bindings = self.list_bindings(slot_id=slot_id, item_id=item_id)
        return InventoryLookupResult(
            slot_id=slot_id,
            item_id=item_id,
            balance=self._to_balance_dto(balance) if balance is not None else None,
            bindings=bindings,
        )

    def list_bindings(self, slot_id: int | None = None, item_id: int | None = None) -> tuple[SlotBindingDTO, ...]:
        statement = select(SlotItemBinding)
        if slot_id is not None:
            statement = statement.where(SlotItemBinding.slot_id == slot_id)
        if item_id is not None:
            statement = statement.where(SlotItemBinding.item_id == item_id)
        bindings = self.inventory_repository.session.execute(statement).scalars()
        return tuple(self._to_binding_dto(binding) for binding in bindings)

    def list_replenishment_options(self) -> tuple[ReplenishmentOptionDTO, ...]:
        statement = (
            select(SlotItemBinding, Item, Slot, InventoryBalance)
            .join(Item, Item.id == SlotItemBinding.item_id)
            .join(Slot, Slot.id == SlotItemBinding.slot_id)
            .outerjoin(
                InventoryBalance,
                (InventoryBalance.slot_id == SlotItemBinding.slot_id)
                & (InventoryBalance.item_id == SlotItemBinding.item_id),
            )
            .where(
                SlotItemBinding.is_active.is_(True),
                Item.status == ItemStatus.ACTIVE,
                Slot.status == SlotStatus.ACTIVE,
            )
            .order_by(Item.name.asc(), Slot.code.asc(), SlotItemBinding.id.asc())
        )
        rows = self.inventory_repository.session.execute(statement)
        return tuple(
            ReplenishmentOptionDTO(
                item_id=item.id,
                item_name=item.name,
                item_sku=item.sku,
                item_unit=item.unit,
                item_min_level=item.min_level,
                slot_id=slot.id,
                slot_code=slot.code,
                slot_status=slot.status.value,
                slot_type=slot.slot_type.value,
                drum_position=slot.drum_position,
                board_address=slot.board_address,
                lock_number=slot.lock_number,
                capacity=slot.capacity,
                binding_type=binding.binding_type,
                quantity=balance.quantity if balance is not None else 0,
                updated_at=balance.updated_at if balance is not None else None,
            )
            for binding, item, slot, balance in rows
        )

    @staticmethod
    def _validate_slot_item_ids(slot_id: int, item_id: int) -> None:
        if slot_id <= 0:
            raise ValidationError("slot_id must be positive")
        if item_id <= 0:
            raise ValidationError("item_id must be positive")

    @staticmethod
    def _to_balance_dto(balance: InventoryBalance) -> InventoryBalanceDTO:
        return InventoryBalanceDTO(
            slot_id=balance.slot_id,
            item_id=balance.item_id,
            quantity=balance.quantity,
            updated_at=balance.updated_at,
        )

    @staticmethod
    def _to_binding_dto(binding: SlotItemBinding) -> SlotBindingDTO:
        return SlotBindingDTO(
            slot_id=binding.slot_id,
            item_id=binding.item_id,
            binding_type=binding.binding_type,
            is_active=binding.is_active,
            valid_from=binding.valid_from,
            valid_to=binding.valid_to,
        )
