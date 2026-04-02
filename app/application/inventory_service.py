from __future__ import annotations

from app.application.dto.inventory import InventoryBalanceDTO, InventoryLookupResult, SlotBindingDTO
from app.application.exceptions import ValidationError
from app.persistence.models import InventoryBalance, SlotItemBinding
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
        if slot_id is not None and slot_id <= 0:
            raise ValidationError("slot_id must be positive")
        if item_id is not None and item_id <= 0:
            raise ValidationError("item_id must be positive")
        return tuple(
            self._to_binding_dto(binding)
            for binding in self.inventory_repository.list_bindings(slot_id=slot_id, item_id=item_id)
        )

    def list_balances(self, slot_id: int | None = None, item_id: int | None = None) -> tuple[InventoryBalanceDTO, ...]:
        if slot_id is not None and slot_id <= 0:
            raise ValidationError("slot_id must be positive")
        if item_id is not None and item_id <= 0:
            raise ValidationError("item_id must be positive")
        return tuple(
            self._to_balance_dto(balance)
            for balance in self.inventory_repository.list_balances(slot_id=slot_id, item_id=item_id)
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
            binding_id=binding.id,
            slot_id=binding.slot_id,
            item_id=binding.item_id,
            binding_type=binding.binding_type,
            is_active=binding.is_active,
            valid_from=binding.valid_from,
            valid_to=binding.valid_to,
        )
