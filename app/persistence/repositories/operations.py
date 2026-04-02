from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select

from app.domain.enums import OperationState
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

    def list_unfinished(self) -> list[Operation]:
        terminal_states = (
            OperationState.COMPLETED,
            OperationState.SESSION_COMPLETED,
            OperationState.DEGRADED_READY,
            OperationState.SYSTEM_READY,
            OperationState.REJECTED,
            OperationState.CANCELLED,
            OperationState.TIMED_OUT,
            OperationState.FAILED,
            OperationState.RECOVERY_REQUIRED,
        )
        statement = select(Operation).where(Operation.operation_state.not_in(terminal_states)).order_by(Operation.id.asc())
        return list(self.session.execute(statement).scalars())

    def list_recovery_scan_candidates(self) -> list[Operation]:
        non_recoverable_terminal_states = (
            OperationState.COMPLETED,
            OperationState.SESSION_COMPLETED,
            OperationState.DEGRADED_READY,
            OperationState.SYSTEM_READY,
            OperationState.REJECTED,
            OperationState.CANCELLED,
            OperationState.TIMED_OUT,
            OperationState.FAILED,
        )
        statement = (
            select(Operation)
            .where(
                or_(
                    Operation.operation_state.not_in(non_recoverable_terminal_states),
                    Operation.operation_state == OperationState.RECOVERY_REQUIRED,
                )
            )
            .order_by(Operation.id.asc())
        )
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

    def list_for_report(
        self,
        *,
        limit: int | None = None,
        operation_type: str | None = None,
        operation_state: str | None = None,
        slot_id: int | None = None,
        item_id: int | None = None,
        user_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[Operation]:
        statement = select(Operation).order_by(Operation.id.asc())
        if operation_type is not None:
            statement = statement.where(Operation.operation_type == operation_type)
        if operation_state is not None:
            statement = statement.where(Operation.operation_state == operation_state)
        if slot_id is not None:
            statement = statement.where(Operation.slot_id == slot_id)
        if item_id is not None:
            statement = statement.where(Operation.item_id == item_id)
        if user_id is not None:
            statement = statement.where(Operation.user_id == user_id)
        if created_from is not None:
            statement = statement.where(Operation.started_at.is_not(None), Operation.started_at >= created_from)
        if created_to is not None:
            statement = statement.where(Operation.started_at.is_not(None), Operation.started_at <= created_to)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.execute(statement).scalars())


class OperationSessionRepository(Repository):
    def get_by_id(self, session_id: int) -> OperationSession | None:
        return self.session.get(OperationSession, session_id)

    def add(self, session: OperationSession) -> None:
        self.session.add(session)
