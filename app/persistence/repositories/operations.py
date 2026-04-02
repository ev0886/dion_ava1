from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import Operation, OperationSession, OperationStateHistory
from app.persistence.repositories.base import Repository


class OperationRepository(Repository):
    def add(self, operation: Operation) -> None:
        self.session.add(operation)

    def get_by_id(self, operation_id: int) -> Operation | None:
        return self.session.get(Operation, operation_id)

    def list_by_session(self, session_id: int) -> list[Operation]:
        statement = select(Operation).where(Operation.session_id == session_id)
        return list(self.session.execute(statement).scalars())

    def add_state_history(self, history_entry: OperationStateHistory) -> None:
        self.session.add(history_entry)

    def list_state_history(self, operation_id: int) -> list[OperationStateHistory]:
        statement = (
            select(OperationStateHistory)
            .where(OperationStateHistory.operation_id == operation_id)
            .order_by(OperationStateHistory.id.asc())
        )
        return list(self.session.execute(statement).scalars())


class OperationSessionRepository(Repository):
    def get_by_id(self, session_id: int) -> OperationSession | None:
        return self.session.get(OperationSession, session_id)

    def add(self, session: OperationSession) -> None:
        self.session.add(session)
