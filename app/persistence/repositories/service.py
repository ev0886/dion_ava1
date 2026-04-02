from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import Export
from app.persistence.models.service import SystemSetting
from app.persistence.repositories.base import Repository


class ExportRepository(Repository):
    def add(self, export: Export) -> None:
        self.session.add(export)

    def get_by_id(self, export_id: int) -> Export | None:
        return self.session.get(Export, export_id)


class SystemSettingRepository(Repository):
    def get_by_key(self, key: str) -> SystemSetting | None:
        statement = select(SystemSetting).where(SystemSetting.key == key)
        return self.session.execute(statement).scalar_one_or_none()

    def list_by_keys(self, keys: tuple[str, ...]) -> list[SystemSetting]:
        statement = select(SystemSetting).where(SystemSetting.key.in_(keys)).order_by(SystemSetting.key.asc())
        return list(self.session.execute(statement).scalars())

    def upsert(
        self,
        *,
        key: str,
        value: str,
        value_type: str,
        description: str | None,
    ) -> SystemSetting:
        row = self.get_by_key(key)
        if row is None:
            row = SystemSetting(
                key=key,
                value=value,
                value_type=value_type,
                description=description,
            )
            self.session.add(row)
            return row
        row.value = value
        row.value_type = value_type
        row.description = description
        return row

    def delete_by_key(self, key: str) -> None:
        row = self.get_by_key(key)
        if row is not None:
            self.session.delete(row)
