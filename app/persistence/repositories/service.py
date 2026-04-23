from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import Export, SystemSetting
from app.persistence.repositories.base import Repository


class ExportRepository(Repository):
    def add(self, export: Export) -> None:
        self.session.add(export)

    def get_by_id(self, export_id: int) -> Export | None:
        return self.session.get(Export, export_id)


class SystemSettingRepository(Repository):
    def get_value(self, key: str) -> str | None:
        statement = select(SystemSetting.value).where(SystemSetting.key == key)
        return self.session.execute(statement).scalar_one_or_none()

    def set_value(
        self,
        *,
        key: str,
        value: str,
        value_type: str = "string",
        description: str | None = None,
    ) -> None:
        statement = select(SystemSetting).where(SystemSetting.key == key)
        setting = self.session.execute(statement).scalar_one_or_none()
        if setting is None:
            self.session.add(
                SystemSetting(
                    key=key,
                    value=value,
                    value_type=value_type,
                    description=description,
                )
            )
            return
        setting.value = value
        setting.value_type = value_type
        setting.description = description
