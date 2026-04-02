from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.persistence.models import Export
from app.persistence.repositories.base import Repository


class ExportRepository(Repository):
    def add(self, export: Export) -> None:
        self.session.add(export)

    def get_by_id(self, export_id: int) -> Export | None:
        return self.session.get(Export, export_id)

    def list_by_destination_path(self, destination_path: str) -> list[Export]:
        statement = select(Export).where(Export.destination_path == destination_path).order_by(Export.id.asc())
        return list(self.session.execute(statement).scalars())

    @staticmethod
    def list_artifacts(file_path: str | None) -> tuple[Path, ...]:
        if file_path is None:
            return ()
        artifact_dir = Path(file_path).parent
        if not artifact_dir.exists() or not artifact_dir.is_dir():
            return ()
        return tuple(sorted(path for path in artifact_dir.iterdir() if path.is_file()))
