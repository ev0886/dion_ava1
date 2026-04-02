from __future__ import annotations

from sqlalchemy import Select, case, select

from app.domain.enums import BindingType, ItemStatus
from app.persistence.models import (
    InventoryBalance,
    InventoryTransaction,
    Item,
    ItemGroup,
    Permission,
    Slot,
    SlotItemBinding,
)
from app.persistence.repositories.base import Repository


class InventoryRepository(Repository):
    def add_item(self, item: Item) -> None:
        self.session.add(item)

    def add_permission(self, permission: Permission) -> None:
        self.session.add(permission)

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

    def get_item(self, item_id: int) -> Item | None:
        return self.session.get(Item, item_id)

    def get_item_by_sku(self, sku: str) -> Item | None:
        statement = select(Item).where(Item.sku == sku)
        return self.session.execute(statement).scalar_one_or_none()

    def get_item_group(self, item_group_id: int) -> ItemGroup | None:
        return self.session.get(ItemGroup, item_group_id)

    def list_items(
        self,
        *,
        item_group_id: int | None = None,
        status: ItemStatus | None = None,
        search: str | None = None,
    ) -> list[Item]:
        statement: Select[tuple[Item]] = select(Item).order_by(Item.id.asc())
        if item_group_id is not None:
            statement = statement.where(Item.item_group_id == item_group_id)
        if status is not None:
            statement = statement.where(Item.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.where((Item.sku.ilike(pattern)) | (Item.name.ilike(pattern)))
        return list(self.session.execute(statement).scalars())

    def list_active_bindings_for_item(self, item_id: int) -> list[SlotItemBinding]:
        statement = (
            select(SlotItemBinding)
            .where(
                SlotItemBinding.item_id == item_id,
                SlotItemBinding.is_active.is_(True),
            )
            .order_by(SlotItemBinding.id.asc())
        )
        return list(self.session.execute(statement).scalars())

    def list_balances_for_item(self, item_id: int) -> list[InventoryBalance]:
        statement = select(InventoryBalance).where(InventoryBalance.item_id == item_id).order_by(InventoryBalance.id.asc())
        return list(self.session.execute(statement).scalars())

    def get_permission(self, permission_id: int) -> Permission | None:
        return self.session.get(Permission, permission_id)

    def list_permissions_for_user(self, user_id: int) -> list[Permission]:
        statement = select(Permission).where(Permission.user_id == user_id).order_by(Permission.id.asc())
        return list(self.session.execute(statement).scalars())

    def find_active_equivalent_permission(
        self,
        *,
        user_id: int,
        item_id: int | None,
        item_group_id: int | None,
        can_dispense: bool,
        can_return: bool,
    ) -> Permission | None:
        statement = select(Permission).where(
            Permission.user_id == user_id,
            Permission.item_id == item_id,
            Permission.item_group_id == item_group_id,
            Permission.can_dispense.is_(can_dispense),
            Permission.can_return.is_(can_return),
            Permission.valid_to.is_(None),
        )
        return self.session.execute(statement).scalar_one_or_none()

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
