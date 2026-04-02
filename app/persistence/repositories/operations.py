from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select

from app.domain.enums import OperationState, OperationType
from app.persistence.models import Operation, OperationSession, OperationStateHistory
from app.persistence.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class OperationDashboardRecord:
    operation_id: int
    operation_type: OperationType
    operation_state: OperationState
    user_id: int | None
    item_id: int | None
    slot_id: int | None
    qty_requested: int
    qty_confirmed: int | None
    result: str | None
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


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

    def count_unfinished(self) -> int:
        statement = select(func.count(Operation.id)).where(Operation.operation_state.not_in(self._terminal_states()))
        return int(self.session.execute(statement).scalar_one())

    def count_recent_problem_operations(self, window_start: datetime) -> int:
        activity_timestamp = func.coalesce(Operation.finished_at, Operation.started_at)
        statement = select(func.count(Operation.id)).where(
            Operation.operation_state.in_((OperationState.FAILED, OperationState.RECOVERY_REQUIRED)),
            activity_timestamp.is_not(None),
            activity_timestamp >= window_start,
        )
        return int(self.session.execute(statement).scalar_one())

    def list_recent_dashboard_operations(
        self,
        *,
        limit: int,
        window_start: datetime,
    ) -> tuple[list[OperationDashboardRecord], int]:
        activity_timestamp = func.coalesce(Operation.finished_at, Operation.started_at)
        base_statement = (
            select(Operation)
            .where(activity_timestamp.is_not(None), activity_timestamp >= window_start)
            .order_by(activity_timestamp.desc(), Operation.id.desc())
        )
        total_count = int(self.session.execute(select(func.count()).select_from(base_statement.subquery())).scalar_one())
        operations = list(self.session.execute(base_statement.limit(limit)).scalars())
        return (
            [
                OperationDashboardRecord(
                    operation_id=operation.id,
                    operation_type=operation.operation_type,
                    operation_state=operation.operation_state,
                    user_id=operation.user_id,
                    item_id=operation.item_id,
                    slot_id=operation.slot_id,
                    qty_requested=operation.qty_requested,
                    qty_confirmed=operation.qty_confirmed,
                    result=operation.result,
                    error_code=operation.error_code,
                    started_at=operation.started_at,
                    finished_at=operation.finished_at,
                )
                for operation in operations
            ],
            total_count,
        )

    @staticmethod
    def _terminal_states() -> tuple[OperationState, ...]:
        return (
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


class OperationSessionRepository(Repository):
    def get_by_id(self, session_id: int) -> OperationSession | None:
        return self.session.get(OperationSession, session_id)

    def add(self, session: OperationSession) -> None:
        self.session.add(session)
