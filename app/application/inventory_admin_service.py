from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.inventory import InventoryAdjustmentResultDTO, InventoryBalanceDTO
from app.application.exceptions import NotFoundError, ValidationError
from app.application.time import utc_now
from app.domain.enums import InventoryTransactionType
from app.persistence.models import AuditLog, InventoryBalance, InventoryTransaction
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository


@dataclass(slots=True)
class InventoryAdminService:
    inventory_repository: InventoryRepository
    audit_log_repository: AuditLogRepository

    def adjust_inventory(
        self,
        *,
        slot_id: int,
        item_id: int,
        quantity_delta: int,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> InventoryAdjustmentResultDTO:
        if quantity_delta == 0:
            raise ValidationError("quantity_delta must not be zero")
        slot = self.inventory_repository.get_slot(self._validate_positive_int(slot_id, field_name="slot_id"))
        if slot is None:
            raise NotFoundError(f"Slot not found: {slot_id}")
        item = self.inventory_repository.get_item(self._validate_positive_int(item_id, field_name="item_id"))
        if item is None:
            raise NotFoundError(f"Item not found: {item_id}")

        balance = self._get_or_create_balance(slot_id=slot.id, item_id=item.id)
        quantity_before = balance.quantity
        quantity_after = quantity_before + quantity_delta
        if quantity_after < 0:
            raise ValidationError("Inventory quantity cannot become negative")

        balance.quantity = quantity_after
        transaction = InventoryTransaction(
            slot_id=slot.id,
            item_id=item.id,
            operation_id=None,
            session_id=None,
            transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
            quantity_delta=quantity_delta,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            comment=comment or "Manual inventory delta adjustment",
            created_at=utc_now(),
        )
        self.inventory_repository.add_transaction(transaction)
        self.inventory_repository.session.flush()
        self._record_audit(
            entity_id=f"{slot.id}:{item.id}",
            action="manual_adjust_delta",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
            before_json={"slot_id": slot.id, "item_id": item.id, "quantity": quantity_before},
            after_json={"slot_id": slot.id, "item_id": item.id, "quantity": quantity_after},
        )
        self.inventory_repository.session.commit()
        return self._to_adjustment_dto(transaction=transaction, balance=balance)

    def set_inventory(
        self,
        *,
        slot_id: int,
        item_id: int,
        quantity: int,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> InventoryAdjustmentResultDTO:
        if quantity < 0:
            raise ValidationError("quantity cannot be negative")
        slot = self.inventory_repository.get_slot(self._validate_positive_int(slot_id, field_name="slot_id"))
        if slot is None:
            raise NotFoundError(f"Slot not found: {slot_id}")
        item = self.inventory_repository.get_item(self._validate_positive_int(item_id, field_name="item_id"))
        if item is None:
            raise NotFoundError(f"Item not found: {item_id}")

        balance = self._get_or_create_balance(slot_id=slot.id, item_id=item.id)
        quantity_before = balance.quantity
        quantity_after = quantity
        balance.quantity = quantity_after
        transaction = InventoryTransaction(
            slot_id=slot.id,
            item_id=item.id,
            operation_id=None,
            session_id=None,
            transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
            quantity_delta=quantity_after - quantity_before,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            comment=comment or "Manual inventory set to exact quantity",
            created_at=utc_now(),
        )
        self.inventory_repository.add_transaction(transaction)
        self.inventory_repository.session.flush()
        self._record_audit(
            entity_id=f"{slot.id}:{item.id}",
            action="manual_set_quantity",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
            before_json={"slot_id": slot.id, "item_id": item.id, "quantity": quantity_before},
            after_json={"slot_id": slot.id, "item_id": item.id, "quantity": quantity_after},
        )
        self.inventory_repository.session.commit()
        return self._to_adjustment_dto(transaction=transaction, balance=balance)

    def _get_or_create_balance(self, *, slot_id: int, item_id: int) -> InventoryBalance:
        balance = self.inventory_repository.get_balance(slot_id, item_id)
        if balance is not None:
            return balance
        balance = InventoryBalance(slot_id=slot_id, item_id=item_id, quantity=0)
        self.inventory_repository.add_balance(balance)
        self.inventory_repository.session.flush()
        return balance

    def _record_audit(
        self,
        *,
        entity_id: str,
        action: str,
        actor_user_id: int | None,
        reason_code: str | None,
        comment: str | None,
        before_json: dict[str, object],
        after_json: dict[str, object],
    ) -> None:
        self.audit_log_repository.add(
            AuditLog(
                entity_type="inventory_balance",
                entity_id=entity_id,
                action=action,
                actor_user_id=actor_user_id,
                reason_code=reason_code,
                comment=comment,
                before_json=before_json,
                after_json=after_json,
            )
        )

    @staticmethod
    def _validate_positive_int(value: int, *, field_name: str) -> int:
        if value <= 0:
            raise ValidationError(f"{field_name} must be positive")
        return value

    @staticmethod
    def _to_adjustment_dto(
        *,
        transaction: InventoryTransaction,
        balance: InventoryBalance,
    ) -> InventoryAdjustmentResultDTO:
        return InventoryAdjustmentResultDTO(
            slot_id=transaction.slot_id,
            item_id=transaction.item_id,
            transaction_type=transaction.transaction_type,
            quantity_delta=transaction.quantity_delta,
            quantity_before=transaction.quantity_before,
            quantity_after=transaction.quantity_after,
            comment=transaction.comment,
            created_at=transaction.created_at,
            balance=InventoryBalanceDTO(
                slot_id=balance.slot_id,
                item_id=balance.item_id,
                quantity=balance.quantity,
                updated_at=balance.updated_at,
            ),
        )
