from __future__ import annotations

from sqlalchemy import func, or_, select

from app.domain.enums import OperationState, OperationType
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

    def list_operations(
        self,
        *,
        limit: int,
        offset: int,
        operation_state: OperationState | None = None,
        operation_type: OperationType | None = None,
        user_id: int | None = None,
        item_id: int | None = None,
        slot_id: int | None = None,
        session_id: int | None = None,
    ) -> list[Operation]:
        statement = select(Operation).order_by(Operation.id.asc()).limit(limit).offset(offset)
        if operation_state is not None:
            statement = statement.where(Operation.operation_state == operation_state)
        if operation_type is not None:
            statement = statement.where(Operation.operation_type == operation_type)
        if user_id is not None:
            statement = statement.where(Operation.user_id == user_id)
        if item_id is not None:
            statement = statement.where(Operation.item_id == item_id)
        if slot_id is not None:
            statement = statement.where(Operation.slot_id == slot_id)
        if session_id is not None:
            statement = statement.where(Operation.session_id == session_id)
        return list(self.session.execute(statement).scalars())

    def count_operations(
        self,
        *,
        operation_state: OperationState | None = None,
        operation_type: OperationType | None = None,
        user_id: int | None = None,
        item_id: int | None = None,
        slot_id: int | None = None,
        session_id: int | None = None,
    ) -> int:
        statement = select(func.count()).select_from(Operation)
        if operation_state is not None:
            statement = statement.where(Operation.operation_state == operation_state)
        if operation_type is not None:
            statement = statement.where(Operation.operation_type == operation_type)
        if user_id is not None:
            statement = statement.where(Operation.user_id == user_id)
        if item_id is not None:
            statement = statement.where(Operation.item_id == item_id)
        if slot_id is not None:
            statement = statement.where(Operation.slot_id == slot_id)
        if session_id is not None:
            statement = statement.where(Operation.session_id == session_id)
        return int(self.session.execute(statement).scalar_one())

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
