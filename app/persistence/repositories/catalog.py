from __future__ import annotations

from sqlalchemy import func, select

from app.domain.enums import ItemStatus, SlotStatus, SlotType
from app.persistence.models import Item, Slot
from app.persistence.repositories.base import Repository


class CatalogRepository(Repository):
    def list_items(
        self,
        *,
        limit: int,
        offset: int,
        status: ItemStatus | None = None,
    ) -> list[Item]:
        statement = select(Item).order_by(Item.id.asc()).limit(limit).offset(offset)
        if status is not None:
            statement = statement.where(Item.status == status)
        return list(self.session.execute(statement).scalars())

    def count_items(self, *, status: ItemStatus | None = None) -> int:
        statement = select(func.count()).select_from(Item)
        if status is not None:
            statement = statement.where(Item.status == status)
        return int(self.session.execute(statement).scalar_one())

    def list_slots(
        self,
        *,
        limit: int,
        offset: int,
        status: SlotStatus | None = None,
        slot_type: SlotType | None = None,
    ) -> list[Slot]:
        statement = select(Slot).order_by(Slot.id.asc()).limit(limit).offset(offset)
        if status is not None:
            statement = statement.where(Slot.status == status)
        if slot_type is not None:
            statement = statement.where(Slot.slot_type == slot_type)
        return list(self.session.execute(statement).scalars())

    def count_slots(
        self,
        *,
        status: SlotStatus | None = None,
        slot_type: SlotType | None = None,
    ) -> int:
        statement = select(func.count()).select_from(Slot)
        if status is not None:
            statement = statement.where(Slot.status == status)
        if slot_type is not None:
            statement = statement.where(Slot.slot_type == slot_type)
        return int(self.session.execute(statement).scalar_one())
