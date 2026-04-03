from __future__ import annotations

from dataclasses import dataclass

from app.application.state_machine import assert_transition_allowed
from app.application.time import utc_now
from app.domain.enums import OperationState, OperationType
from app.hardware.exceptions import HardwareBusyError, HardwareError, HardwareFailureError, HardwareTimeoutError
from app.persistence.models import Operation, OperationStateHistory
from app.persistence.repositories.operations import OperationRepository


@dataclass(slots=True)
class OperationRecorder:
    operation_repository: OperationRepository

    def create_operation(
        self,
        operation: Operation,
        *,
        comment: str,
        context: dict[str, object] | None = None,
    ) -> Operation:
        self.operation_repository.add(operation)
        self.operation_repository.session.flush()
        self._append_history(operation.id, operation.operation_state, comment=comment, context=context)
        return operation

    def transition(
        self,
        operation: Operation,
        target_state: OperationState,
        *,
        comment: str,
        history_context: dict[str, object] | None = None,
        hardware_context: dict[str, object] | None = None,
        business_context: dict[str, object] | None = None,
        result: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        qty_confirmed: int | None = None,
        finished: bool = False,
    ) -> Operation:
        assert_transition_allowed(operation.operation_type, operation.operation_state, target_state)
        operation.operation_state = target_state
        if hardware_context:
            operation.hardware_context_json = {**dict(operation.hardware_context_json or {}), **hardware_context}
        if business_context:
            operation.business_context_json = {**dict(operation.business_context_json or {}), **business_context}
        if result is not None:
            operation.result = result
        if error_code is not None:
            operation.error_code = error_code
        if error_message is not None:
            operation.error_message = error_message
        if qty_confirmed is not None:
            operation.qty_confirmed = qty_confirmed
        if finished:
            operation.finished_at = utc_now()
        self._append_history(operation.id, target_state, comment=comment, context=history_context)
        self.operation_repository.session.flush()
        return operation

    def record_hardware_failure(
        self,
        operation: Operation,
        error: HardwareError,
        *,
        recovery_required: bool,
        comment: str,
    ) -> Operation:
        target_state = OperationState.RECOVERY_REQUIRED if recovery_required else OperationState.FAILED
        hardware_context = {
            "hardware_error": {
                "device_type": error.device_type.value,
                "operation": error.operation,
                "message": str(error),
            }
        }
        return self.transition(
            operation,
            target_state,
            comment=comment,
            history_context=hardware_context,
            hardware_context=hardware_context,
            result="hardware_error",
            error_code=self.error_code_for_exception(error),
            error_message=str(error),
            finished=True,
        )

    def recover_to_terminal(
        self,
        operation: Operation,
        target_state: OperationState,
        *,
        comment: str,
        history_context: dict[str, object] | None = None,
        result: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        qty_confirmed: int | None = None,
        clear_error: bool = False,
    ) -> Operation:
        if target_state not in self._allowed_manual_recovery_terminal_states(operation.operation_type):
            raise ValueError(
                f"Unsupported manual recovery target for {operation.operation_type.value}: {target_state.value}"
            )
        operation.operation_state = target_state
        if result is not None:
            operation.result = result
        if clear_error:
            operation.error_code = None
            operation.error_message = None
        if error_code is not None:
            operation.error_code = error_code
        if error_message is not None:
            operation.error_message = error_message
        if qty_confirmed is not None:
            operation.qty_confirmed = qty_confirmed
        operation.finished_at = operation.finished_at or utc_now()
        self._append_history(operation.id, target_state, comment=comment, context=history_context)
        self.operation_repository.session.flush()
        return operation

    @staticmethod
    def _allowed_manual_recovery_terminal_states(operation_type: OperationType) -> tuple[OperationState, ...]:
        if operation_type is OperationType.REFILL_ITEM:
            return (OperationState.SESSION_COMPLETED, OperationState.CANCELLED, OperationState.FAILED)
        return (OperationState.COMPLETED, OperationState.CANCELLED, OperationState.FAILED)

    @staticmethod
    def error_code_for_exception(error: HardwareError) -> str:
        if isinstance(error, HardwareBusyError):
            return "hardware_busy"
        if isinstance(error, HardwareTimeoutError):
            return "hardware_timeout"
        if isinstance(error, HardwareFailureError):
            return "hardware_failure"
        return "hardware_error"

    def _append_history(
        self,
        operation_id: int | None,
        state: OperationState,
        *,
        comment: str,
        context: dict[str, object] | None,
    ) -> None:
        if operation_id is None:
            raise ValueError("operation_id must be assigned before history is recorded")
        self.operation_repository.add_state_history(
            OperationStateHistory(
                operation_id=operation_id,
                state=state,
                comment=comment,
                context_json=dict(context or {}),
            )
        )
