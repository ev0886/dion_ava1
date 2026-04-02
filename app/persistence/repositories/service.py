from __future__ import annotations

from app.persistence.models import Export
from app.persistence.repositories.base import Repository


class ExportRepository(Repository):
    def add(self, export: Export) -> None:
        self.session.add(export)

    def get_by_id(self, export_id: int) -> Export | None:
        return self.session.get(Export, export_id)
