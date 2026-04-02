from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import InventoryBalance, InventoryTransaction
from app.persistence.repositories.base import Repository


class InventoryRepository(Repository):
    def get_balance(self, slot_id: int, item_id: int) -> InventoryBalance | None:
        statement = select(InventoryBalance).where(
            InventoryBalance.slot_id == slot_id,
            InventoryBalance.item_id == item_id,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def add_transaction(self, transaction: InventoryTransaction) -> None:
        self.session.add(transaction)
