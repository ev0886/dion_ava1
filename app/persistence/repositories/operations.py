from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select

from app.application.dto.admin import AdminOperationExportRowDTO, AdminRecentOperationDTO
from app.domain.enums import OperationState, OperationType
from app.persistence.models import Item, Operation, OperationSession, OperationStateHistory, Slot, User
from app.persistence.repositories.base import Repository


class OperationRepository(Repository):
    _ADMIN_PROBLEM_OPERATION_STATES: tuple[OperationState, ...] = (
        OperationState.RECOVERY_REQUIRED,
        OperationState.FAILED,
    )

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

    def has_completed_dispense_for_user_between(
        self,
        *,
        user_id: int,
        started_at: datetime,
        finished_before: datetime,
    ) -> bool:
        statement = (
            select(Operation.id)
            .where(Operation.user_id == user_id)
            .where(Operation.operation_type == OperationType.DISPENSE)
            .where(Operation.operation_state == OperationState.COMPLETED)
            .where(
                and_(
                    Operation.finished_at.is_not(None),
                    Operation.finished_at >= started_at,
                    Operation.finished_at < finished_before,
                )
            )
            .limit(1)
        )
        return self.session.execute(statement).scalar_one_or_none() is not None

    def list_recent_for_admin(self, *, limit: int = 20) -> list[AdminRecentOperationDTO]:
        rows = self.session.execute(self._admin_operation_list_statement(limit=limit)).all()
        return [
            AdminRecentOperationDTO(
                operation_id=operation_id,
                started_at=started_at,
                operation_type=operation_type,
                operation_state=operation_state,
                user_code=user_code,
                user_full_name=full_name,
                item_name=item_name,
                quantity=qty_confirmed if qty_confirmed is not None else qty_requested,
                slot_code=slot_code,
            )
            for operation_id, started_at, operation_type, operation_state, user_code, full_name, item_name, qty_confirmed, qty_requested, slot_code in rows
        ]

    def list_problem_for_admin(self, *, limit: int = 20) -> list[AdminRecentOperationDTO]:
        rows = self.session.execute(
            self._admin_operation_list_statement(
                limit=limit,
                problem_states=self._ADMIN_PROBLEM_OPERATION_STATES,
            )
        ).all()
        return [
            AdminRecentOperationDTO(
                operation_id=operation_id,
                started_at=started_at,
                operation_type=operation_type,
                operation_state=operation_state,
                user_code=user_code,
                user_full_name=full_name,
                item_name=item_name,
                quantity=qty_confirmed if qty_confirmed is not None else qty_requested,
                slot_code=slot_code,
            )
            for operation_id, started_at, operation_type, operation_state, user_code, full_name, item_name, qty_confirmed, qty_requested, slot_code in rows
        ]

    def list_for_admin_export(
        self,
        *,
        date_from: date,
        date_to: date,
    ) -> list[AdminOperationExportRowDTO]:
        range_start = datetime.combine(date_from, time.min)
        range_end = datetime.combine(date_to + timedelta(days=1), time.min)
        anchor_timestamp = func.coalesce(Operation.started_at, Operation.finished_at)
        rows = self.session.execute(
            select(
                Operation.id,
                Operation.started_at,
                Operation.finished_at,
                Operation.operation_type,
                Operation.operation_state,
                User.user_code,
                User.full_name,
                Item.name,
                Operation.qty_confirmed,
                Operation.qty_requested,
                Slot.code,
                Operation.result,
                Operation.error_code,
                Operation.error_message,
            )
            .outerjoin(User, User.id == Operation.user_id)
            .outerjoin(Item, Item.id == Operation.item_id)
            .outerjoin(Slot, Slot.id == Operation.slot_id)
            .where(anchor_timestamp.is_not(None))
            .where(anchor_timestamp >= range_start)
            .where(anchor_timestamp < range_end)
            .order_by(anchor_timestamp.asc(), Operation.id.asc())
        ).all()
        return [
            AdminOperationExportRowDTO(
                operation_id=operation_id,
                started_at=started_at,
                finished_at=finished_at,
                operation_type=operation_type,
                operation_state=operation_state,
                user_code=user_code,
                user_full_name=full_name,
                item_name=item_name,
                quantity=qty_confirmed if qty_confirmed is not None else qty_requested,
                slot_code=slot_code,
                result=result,
                error_code=error_code,
                error_message=error_message,
            )
            for (
                operation_id,
                started_at,
                finished_at,
                operation_type,
                operation_state,
                user_code,
                full_name,
                item_name,
                qty_confirmed,
                qty_requested,
                slot_code,
                result,
                error_code,
                error_message,
            ) in rows
        ]

    def _admin_operation_list_statement(
        self,
        *,
        limit: int,
        problem_states: tuple[OperationState, ...] | None = None,
    ):
        statement = (
            select(
                Operation.id,
                Operation.started_at,
                Operation.operation_type,
                Operation.operation_state,
                User.user_code,
                User.full_name,
                Item.name,
                Operation.qty_confirmed,
                Operation.qty_requested,
                Slot.code,
            )
            .outerjoin(User, User.id == Operation.user_id)
            .outerjoin(Item, Item.id == Operation.item_id)
            .outerjoin(Slot, Slot.id == Operation.slot_id)
        )
        if problem_states is not None:
            statement = statement.where(Operation.operation_state.in_(problem_states))
        return statement.order_by(func.coalesce(Operation.started_at, Operation.finished_at).desc(), Operation.id.desc()).limit(limit)


class OperationSessionRepository(Repository):
    def get_by_id(self, session_id: int) -> OperationSession | None:
        return self.session.get(OperationSession, session_id)

    def add(self, session: OperationSession) -> None:
        self.session.add(session)
