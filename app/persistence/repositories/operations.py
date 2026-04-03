from __future__ import annotations

from sqlalchemy import case, or_, select

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

    def list_recent_failures(self, *, limit: int = 20) -> list[Operation]:
        statement = (
            select(Operation)
            .where(
                Operation.operation_state.in_((OperationState.FAILED, OperationState.RECOVERY_REQUIRED)),
            )
            .order_by(
                case((Operation.finished_at.is_(None), 1), else_=0).asc(),
                Operation.finished_at.desc(),
                Operation.id.desc(),
            )
            .limit(limit)
        )
        return list(self.session.execute(statement).scalars())


class OperationSessionRepository(Repository):
    def get_by_id(self, session_id: int) -> OperationSession | None:
        return self.session.get(OperationSession, session_id)

    def add(self, session: OperationSession) -> None:
        self.session.add(session)
