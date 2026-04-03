from __future__ import annotations

from sqlalchemy import select

from app.domain.enums import ExportStatus
from app.persistence.models import Export
from app.persistence.repositories.base import Repository


class ExportRepository(Repository):
    def add(self, export: Export) -> None:
        self.session.add(export)

    def get_by_id(self, export_id: int) -> Export | None:
        return self.session.get(Export, export_id)

    def list_recent_failures(self, *, limit: int = 20) -> list[Export]:
        statement = (
            select(Export)
            .where(Export.status == ExportStatus.FAILED)
            .order_by(Export.id.desc())
            .limit(limit)
        )
        return list(self.session.execute(statement).scalars())
