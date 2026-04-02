from __future__ import annotations

from sqlalchemy import select

from app.application.dto.operations import TransitionCheckResult
from app.application.dto.recovery import RecoveryCaseDTO, RecoveryContextDTO, RecoveryScanResult
from app.application.exceptions import RecoveryError
from app.application.state_machine import assert_transition_allowed, can_transition
from app.domain.enums import OperationState, OperationType
from app.persistence.models import Operation, RecoveryCase
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository


class RecoveryService:
    def __init__(
        self,
        recovery_repository: RecoveryRepository,
        operation_repository: OperationRepository,
    ) -> None:
        self.recovery_repository = recovery_repository
        self.operation_repository = operation_repository

    def get_case(self, recovery_case_id: int) -> RecoveryCaseDTO:
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            raise RecoveryError(f"Recovery case not found: {recovery_case_id}")
        return self._to_dto(recovery_case)

    def list_open_cases(self) -> tuple[RecoveryCaseDTO, ...]:
        return tuple(self._to_dto(case) for case in self.recovery_repository.list_open_cases())

    def scan_recovery_targets(self) -> RecoveryScanResult:
        open_cases = self.list_open_cases()
        unfinished_operation_ids = self._list_unfinished_operation_ids()
        return RecoveryScanResult(
            open_case_count=len(open_cases),
            open_cases=open_cases,
            unfinished_operation_ids=unfinished_operation_ids,
        )

    def assert_transition_allowed(self, current_state: OperationState, target_state: OperationState) -> None:
        assert_transition_allowed(OperationType.RECOVERY, current_state, target_state)

    def check_transition(self, current_state: OperationState, target_state: OperationState) -> TransitionCheckResult:
        return TransitionCheckResult(
            operation_type=OperationType.RECOVERY,
            current_state=current_state,
            target_state=target_state,
            allowed=can_transition(OperationType.RECOVERY, current_state, target_state),
        )

    def build_recovery_context(self, recovery_case_id: int) -> RecoveryContextDTO:
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            raise RecoveryError(f"Recovery case not found: {recovery_case_id}")
        return RecoveryContextDTO(
            recovery_case_id=recovery_case.id,
            summary=recovery_case.summary,
            context=dict(recovery_case.context_json or {}),
        )

    def _list_unfinished_operation_ids(self) -> tuple[int, ...]:
        terminal_states = (
            OperationState.COMPLETED,
            OperationState.SESSION_COMPLETED,
            OperationState.DEGRADED_READY,
            OperationState.SYSTEM_READY,
            OperationState.REJECTED,
            OperationState.CANCELLED,
            OperationState.TIMED_OUT,
            OperationState.FAILED,
        )
        statement = select(Operation.id).where(Operation.operation_state.not_in(terminal_states))
        ids = self.operation_repository.session.execute(statement).scalars()
        return tuple(ids)

    @staticmethod
    def _to_dto(recovery_case: RecoveryCase) -> RecoveryCaseDTO:
        return RecoveryCaseDTO(
            recovery_case_id=recovery_case.id,
            classification=recovery_case.classification,
            status=recovery_case.status,
            summary=recovery_case.summary,
            context=dict(recovery_case.context_json or {}),
            created_at=recovery_case.created_at,
            resolved_at=recovery_case.resolved_at,
        )
