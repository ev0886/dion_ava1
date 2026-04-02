from __future__ import annotations

from sqlalchemy import case, select

from app.domain.enums import BindingType
from app.persistence.models import InventoryBalance, InventoryTransaction, Item, Slot, SlotItemBinding
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

    def get_slot_by_code(self, code: str) -> Slot | None:
        statement = select(Slot).where(Slot.code == code)
        return self.session.execute(statement).scalar_one_or_none()

    def list_slots(self) -> list[Slot]:
        statement = select(Slot).order_by(Slot.id.asc())
        return list(self.session.execute(statement).scalars())

    def add_slot(self, slot: Slot) -> None:
        self.session.add(slot)

    def get_item(self, item_id: int) -> Item | None:
        return self.session.get(Item, item_id)

    def get_binding(self, binding_id: int) -> SlotItemBinding | None:
        return self.session.get(SlotItemBinding, binding_id)

    def find_binding(self, *, slot_id: int, item_id: int, binding_type: BindingType) -> SlotItemBinding | None:
        statement = select(SlotItemBinding).where(
            SlotItemBinding.slot_id == slot_id,
            SlotItemBinding.item_id == item_id,
            SlotItemBinding.binding_type == binding_type,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def list_bindings(
        self,
        *,
        slot_id: int | None = None,
        item_id: int | None = None,
        is_active: bool | None = None,
    ) -> list[SlotItemBinding]:
        statement = select(SlotItemBinding).order_by(SlotItemBinding.id.asc())
        if slot_id is not None:
            statement = statement.where(SlotItemBinding.slot_id == slot_id)
        if item_id is not None:
            statement = statement.where(SlotItemBinding.item_id == item_id)
        if is_active is not None:
            statement = statement.where(SlotItemBinding.is_active.is_(is_active))
        return list(self.session.execute(statement).scalars())

    def add_binding(self, binding: SlotItemBinding) -> None:
        self.session.add(binding)

    def list_balances(
        self,
        *,
        slot_id: int | None = None,
        item_id: int | None = None,
    ) -> list[InventoryBalance]:
        statement = select(InventoryBalance).order_by(InventoryBalance.id.asc())
        if slot_id is not None:
            statement = statement.where(InventoryBalance.slot_id == slot_id)
        if item_id is not None:
            statement = statement.where(InventoryBalance.item_id == item_id)
        return list(self.session.execute(statement).scalars())

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
