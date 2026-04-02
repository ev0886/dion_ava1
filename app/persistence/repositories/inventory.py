from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, select

from app.domain.enums import BindingType
from app.persistence.models import InventoryBalance, InventoryTransaction, Slot, SlotItemBinding
from app.persistence.repositories.base import Repository


class InventoryRepository(Repository):
    def get_balance(self, slot_id: int, item_id: int) -> InventoryBalance | None:
        statement = select(InventoryBalance).where(
            InventoryBalance.slot_id == slot_id,
            InventoryBalance.item_id == item_id,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def add_balance(self, balance: InventoryBalance) -> None:
        self.session.add(balance)

    def add_transaction(self, transaction: InventoryTransaction) -> None:
        self.session.add(transaction)

    def get_slot(self, slot_id: int) -> Slot | None:
        return self.session.get(Slot, slot_id)

    def find_preferred_binding_for_item(self, item_id: int) -> SlotItemBinding | None:
        statement = (
            select(SlotItemBinding)
            .where(
                SlotItemBinding.item_id == item_id,
                SlotItemBinding.is_active.is_(True),
                SlotItemBinding.binding_type.in_((BindingType.RETURN, BindingType.PRIMARY)),
            )
            .order_by(
                case(
                    (SlotItemBinding.binding_type == BindingType.RETURN, 0),
                    else_=1,
                ),
                SlotItemBinding.id.asc(),
            )
        )
        return self.session.execute(statement).scalars().first()

    def list_transactions(self, operation_id: int | None = None) -> list[InventoryTransaction]:
        statement = select(InventoryTransaction).order_by(InventoryTransaction.id.asc())
        if operation_id is not None:
            statement = statement.where(InventoryTransaction.operation_id == operation_id)
        return list(self.session.execute(statement).scalars())

    def list_balances_for_report(
        self,
        *,
        limit: int | None = None,
        slot_id: int | None = None,
        item_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[InventoryBalance]:
        statement = select(InventoryBalance).order_by(InventoryBalance.id.asc())
        if slot_id is not None:
            statement = statement.where(InventoryBalance.slot_id == slot_id)
        if item_id is not None:
            statement = statement.where(InventoryBalance.item_id == item_id)
        if created_from is not None:
            statement = statement.where(InventoryBalance.updated_at >= created_from)
        if created_to is not None:
            statement = statement.where(InventoryBalance.updated_at <= created_to)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.execute(statement).scalars())
