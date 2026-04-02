from __future__ import annotations

from dataclasses import dataclass
from app.application.exceptions import ValidationError
from app.application.dto.operations import RefillMode
from app.application.time import utc_now
from app.domain.enums import InventoryTransactionType
from app.persistence.models import InventoryBalance, InventoryTransaction, Operation
from app.persistence.repositories.inventory import InventoryRepository


@dataclass(slots=True)
class InventoryMutationService:
    inventory_repository: InventoryRepository

    def apply_dispense(self, operation: Operation, quantity: int) -> InventoryBalance:
        balance = self._require_balance(operation)
        if balance.quantity < quantity:
            raise ValidationError("Requested quantity exceeds current balance")
        return self._apply_delta(
            operation=operation,
            balance=balance,
            quantity_delta=-quantity,
            transaction_type=InventoryTransactionType.DISPENSE_DEBIT,
            comment="Dispense inventory committed",
        )

    def apply_return(self, operation: Operation, quantity: int) -> InventoryBalance:
        balance = self._get_or_create_balance(operation)
        return self._apply_delta(
            operation=operation,
            balance=balance,
            quantity_delta=quantity,
            transaction_type=InventoryTransactionType.RETURN_CREDIT,
            comment="Return inventory committed",
        )

    def apply_refill(self, operation: Operation, quantity: int, mode: RefillMode) -> InventoryBalance:
        balance = self._get_or_create_balance(operation)
        quantity_before = balance.quantity
        quantity_after = quantity if mode == "set" else balance.quantity + quantity
        transaction_type = (
            InventoryTransactionType.REFILL_SET if mode == "set" else InventoryTransactionType.REFILL_ADD
        )
        balance.quantity = quantity_after
        self.inventory_repository.add_transaction(
            InventoryTransaction(
                slot_id=balance.slot_id,
                item_id=balance.item_id,
                operation_id=operation.id,
                session_id=operation.session_id,
                transaction_type=transaction_type,
                quantity_delta=quantity_after - quantity_before,
                quantity_before=quantity_before,
                quantity_after=quantity_after,
                comment=f"Refill inventory committed via {mode} mode",
                created_at=utc_now(),
            )
        )
        self.inventory_repository.session.flush()
        return balance

    def _apply_delta(
        self,
        *,
        operation: Operation,
        balance: InventoryBalance,
        quantity_delta: int,
        transaction_type: InventoryTransactionType,
        comment: str,
    ) -> InventoryBalance:
        quantity_before = balance.quantity
        quantity_after = quantity_before + quantity_delta
        if quantity_after < 0:
            raise ValidationError("Inventory quantity cannot become negative")
        balance.quantity = quantity_after
        self.inventory_repository.add_transaction(
            InventoryTransaction(
                slot_id=balance.slot_id,
                item_id=balance.item_id,
                operation_id=operation.id,
                session_id=operation.session_id,
                transaction_type=transaction_type,
                quantity_delta=quantity_delta,
                quantity_before=quantity_before,
                quantity_after=quantity_after,
                comment=comment,
                created_at=utc_now(),
            )
        )
        self.inventory_repository.session.flush()
        return balance

    def _require_balance(self, operation: Operation) -> InventoryBalance:
        balance = self._find_balance(operation)
        if balance is None:
            raise ValidationError("No inventory balance found for slot/item")
        return balance

    def _get_or_create_balance(self, operation: Operation) -> InventoryBalance:
        balance = self._find_balance(operation)
        if balance is not None:
            return balance
        if operation.slot_id is None or operation.item_id is None:
            raise ValidationError("slot_id and item_id are required for inventory writes")
        balance = InventoryBalance(slot_id=operation.slot_id, item_id=operation.item_id, quantity=0)
        self.inventory_repository.add_balance(balance)
        self.inventory_repository.session.flush()
        return balance

    def _find_balance(self, operation: Operation) -> InventoryBalance | None:
        if operation.slot_id is None or operation.item_id is None:
            raise ValidationError("slot_id and item_id are required for inventory writes")
        return self.inventory_repository.get_balance(operation.slot_id, operation.item_id)
