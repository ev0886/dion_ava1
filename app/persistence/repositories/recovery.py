from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import RecoveryCase
from app.persistence.repositories.base import Repository


class RecoveryRepository(Repository):
    def get_by_id(self, recovery_case_id: int) -> RecoveryCase | None:
        return self.session.get(RecoveryCase, recovery_case_id)

    def list_open_cases(self) -> list[RecoveryCase]:
        statement = select(RecoveryCase).where(RecoveryCase.resolved_at.is_(None))
        return list(self.session.execute(statement).scalars())
