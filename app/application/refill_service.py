from __future__ import annotations

from datetime import datetime

from app.application.dto.operations import (
    CreateOperationCommand,
    OperationContextDTO,
    OperationDTO,
    OperationValidationResult,
    RefillRequest,
    TransitionCheckResult,
)
from app.application.exceptions import ValidationError
from app.application.state_machine import assert_transition_allowed, can_transition
from app.domain.enums import OperationState, OperationType
from app.persistence.models import Operation
from app.persistence.repositories.operations import OperationRepository


class RefillOperationService:
    def __init__(self, operation_repository: OperationRepository) -> None:
        self.operation_repository = operation_repository

    def validate_request(self, request: RefillRequest) -> OperationValidationResult:
        if request.quantity < 0:
            raise ValidationError("quantity must be non-negative")
        return OperationValidationResult(
            operation_type=OperationType.REFILL_ITEM,
            valid=True,
            messages=(),
        )

    def create_operation(self, command: CreateOperationCommand) -> OperationDTO:
        operation = Operation(
            session_id=command.session_id,
            operation_type=OperationType.REFILL_ITEM,
            operation_state=command.operation_state,
            user_id=command.user_id,
            item_id=command.item_id,
            slot_id=command.slot_id,
            qty_requested=command.qty_requested,
            qty_confirmed=None,
            result=None,
            error_code=None,
            error_message=None,
            hardware_context_json=dict(command.hardware_context),
            business_context_json=dict(command.business_context),
            started_at=datetime.utcnow(),
            finished_at=None,
        )
        self.operation_repository.session.add(operation)
        return self._to_dto(operation)

    def assert_transition_allowed(self, current_state: OperationState, target_state: OperationState) -> None:
        assert_transition_allowed(OperationType.REFILL_ITEM, current_state, target_state)

    def check_transition(self, current_state: OperationState, target_state: OperationState) -> TransitionCheckResult:
        return TransitionCheckResult(
            operation_type=OperationType.REFILL_ITEM,
            current_state=current_state,
            target_state=target_state,
            allowed=can_transition(OperationType.REFILL_ITEM, current_state, target_state),
        )

    def build_operation_context(self, request: RefillRequest) -> OperationContextDTO:
        return OperationContextDTO(
            operation_type=OperationType.REFILL_ITEM,
            user_id=request.operator_user_id,
            item_id=request.item_id,
            slot_id=request.slot_id,
            session_id=request.session_id,
            operation_state=OperationState.CREATED,
            business_context={"requested_quantity": request.quantity, "mode": request.mode},
            hardware_context={},
        )

    @staticmethod
    def _to_dto(operation: Operation) -> OperationDTO:
        return OperationDTO(
            operation_id=operation.id,
            session_id=operation.session_id,
            operation_type=operation.operation_type,
            operation_state=operation.operation_state,
            user_id=operation.user_id,
            item_id=operation.item_id,
            slot_id=operation.slot_id,
            qty_requested=operation.qty_requested,
            qty_confirmed=operation.qty_confirmed,
            result=operation.result,
            error_code=operation.error_code,
            error_message=operation.error_message,
            hardware_context=dict(operation.hardware_context_json or {}),
            business_context=dict(operation.business_context_json or {}),
            started_at=operation.started_at,
            finished_at=operation.finished_at,
        )
