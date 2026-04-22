from __future__ import annotations

from sqlalchemy import select

from app.application.dto.admin import AdminNomenclatureRecordDTO
from app.domain.enums import ItemStatus
from app.persistence.models import Item, NomenclatureEntry
from app.persistence.repositories.base import Repository


class NomenclatureRepository(Repository):
    DEFAULT_SYNC_ITEM_UNIT = "pcs"

    def list_for_admin(self) -> list[AdminNomenclatureRecordDTO]:
        statement = select(NomenclatureEntry).order_by(NomenclatureEntry.name.asc(), NomenclatureEntry.id.asc())
        entries = self.session.execute(statement).scalars().all()
        return [self._to_admin_record(entry) for entry in entries]

    def list_active(self) -> list[AdminNomenclatureRecordDTO]:
        statement = (
            select(NomenclatureEntry)
            .where(NomenclatureEntry.is_active.is_(True))
            .order_by(NomenclatureEntry.name.asc(), NomenclatureEntry.id.asc())
        )
        entries = self.session.execute(statement).scalars().all()
        return [self._to_admin_record(entry) for entry in entries]

    def get_by_id(self, nomenclature_id: int) -> NomenclatureEntry | None:
        return self.session.get(NomenclatureEntry, nomenclature_id)

    def get_by_normalized_name(self, normalized_name: str) -> NomenclatureEntry | None:
        statement = select(NomenclatureEntry).where(NomenclatureEntry.normalized_name == normalized_name)
        return self.session.execute(statement).scalar_one_or_none()

    def create(self, *, name: str, normalized_name: str, is_active: bool) -> NomenclatureEntry:
        entry = NomenclatureEntry(
            name=name,
            normalized_name=normalized_name,
            is_active=is_active,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    @staticmethod
    def _to_admin_record(entry: NomenclatureEntry) -> AdminNomenclatureRecordDTO:
        return AdminNomenclatureRecordDTO(
            id=entry.id,
            name=entry.name,
            is_active=entry.is_active,
        )

    def get_admin_record(self, nomenclature_id: int) -> AdminNomenclatureRecordDTO:
        entry = self.get_by_id(nomenclature_id)
        if entry is None:
            raise LookupError(f"Nomenclature entry not found: {nomenclature_id}")
        return self._to_admin_record(entry)

    def ensure_active_item_for_entry(self, entry: NomenclatureEntry) -> Item | None:
        sync_item = self._get_item_by_sync_sku(entry.id)
        if sync_item is not None:
            sync_item.name = entry.name
            sync_item.status = ItemStatus.ACTIVE
            return sync_item

        active_name_matches = self._list_active_items_by_normalized_name(entry.normalized_name)
        if active_name_matches:
            return active_name_matches[0]

        created = Item(
            item_group_id=None,
            sku=self._sync_item_sku(entry.id),
            name=entry.name,
            description=None,
            unit=self.DEFAULT_SYNC_ITEM_UNIT,
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        self.session.add(created)
        self.session.flush()
        return created

    def sync_item_for_entry_rename(self, entry: NomenclatureEntry, *, previous_normalized_name: str) -> Item | None:
        sync_item = self._get_item_by_sync_sku(entry.id)
        if sync_item is not None:
            sync_item.name = entry.name
            sync_item.status = ItemStatus.ACTIVE
            return sync_item

        active_name_matches = self._list_active_items_by_normalized_name(entry.normalized_name)
        if active_name_matches:
            return active_name_matches[0]

        previous_matches = self._list_active_items_by_normalized_name(previous_normalized_name)
        if len(previous_matches) == 1:
            previous_matches[0].name = entry.name
            return previous_matches[0]

        return self.ensure_active_item_for_entry(entry)

    @classmethod
    def sync_item_sku(cls, nomenclature_id: int) -> str:
        return cls._sync_item_sku(nomenclature_id)

    @staticmethod
    def _normalize_item_name(name: str) -> str:
        return " ".join(name.split()).casefold()

    @classmethod
    def _sync_item_sku(cls, nomenclature_id: int) -> str:
        return f"nomenclature-{nomenclature_id}"

    def _get_item_by_sync_sku(self, nomenclature_id: int) -> Item | None:
        statement = select(Item).where(Item.sku == self._sync_item_sku(nomenclature_id))
        return self.session.execute(statement).scalar_one_or_none()

    def _list_active_items_by_normalized_name(self, normalized_name: str) -> tuple[Item, ...]:
        statement = (
            select(Item)
            .where(Item.status == ItemStatus.ACTIVE)
            .order_by(Item.id.asc())
        )
        return tuple(
            item
            for item in self.session.execute(statement).scalars()
            if self._normalize_item_name(item.name) == normalized_name
        )
