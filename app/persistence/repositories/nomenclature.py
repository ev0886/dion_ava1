from __future__ import annotations

from sqlalchemy import select

from app.application.dto.admin import AdminNomenclatureRecordDTO
from app.persistence.models import NomenclatureEntry
from app.persistence.repositories.base import Repository


class NomenclatureRepository(Repository):
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
