from __future__ import annotations

from sqlalchemy import case, or_, select

from app.domain.enums import BindingType
from app.persistence.models import InventoryBalance, InventoryTransaction, Item, Permission, Slot, SlotItemBinding
from app.persistence.repositories.base import Repository


class InventoryRepository(Repository):
    def get_item(self, item_id: int) -> Item | None:
        return self.session.get(Item, item_id)

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

    def get_slot_item_binding(
        self,
        slot_id: int,
        item_id: int,
        *,
        allowed_binding_types: tuple[BindingType, ...] | None = None,
    ) -> SlotItemBinding | None:
        statement = select(SlotItemBinding).where(
            SlotItemBinding.slot_id == slot_id,
            SlotItemBinding.item_id == item_id,
            SlotItemBinding.is_active.is_(True),
        )
        if allowed_binding_types:
            statement = statement.where(SlotItemBinding.binding_type.in_(allowed_binding_types))
        statement = statement.order_by(SlotItemBinding.id.asc())
        return self.session.execute(statement).scalars().first()

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

    def find_permission_for_action(
        self,
        *,
        user_id: int,
        item_id: int,
        item_group_id: int | None,
        action: str,
    ) -> Permission | None:
        permission_scope = [Permission.item_id == item_id, Permission.item_id.is_(None) & Permission.item_group_id.is_(None)]
        order_by = [case((Permission.item_id == item_id, 0), else_=1)]
        if item_group_id is not None:
            permission_scope.append(Permission.item_group_id == item_group_id)
            order_by.append(case((Permission.item_group_id == item_group_id, 0), else_=1))
        else:
            order_by.append(case((Permission.item_group_id.is_(None), 0), else_=1))
        statement = (
            select(Permission)
            .where(
                Permission.user_id == user_id,
                or_(*permission_scope),
            )
            .order_by(
                *order_by,
                Permission.id.asc(),
            )
        )
        for permission in self.session.execute(statement).scalars():
            if action == "dispense" and permission.can_dispense:
                return permission
            if action == "return" and permission.can_return:
                return permission
        return None

    def list_transactions(self, operation_id: int | None = None) -> list[InventoryTransaction]:
        statement = select(InventoryTransaction).order_by(InventoryTransaction.id.asc())
        if operation_id is not None:
            statement = statement.where(InventoryTransaction.operation_id == operation_id)
        return list(self.session.execute(statement).scalars())
