from __future__ import annotations

from dataclasses import dataclass, field
from app.application.authorization_service import AuthorizationService
from app.application.dto.auth import AuthorizationRequest
from app.application.dto.operations import (
    CreateOperationCommand,
    OperationContextDTO,
    OperationDTO,
    OperationValidationResult,
    RefillRequest,
    TransitionCheckResult,
)
from app.application.exceptions import NotFoundError, ValidationError
from app.domain.enums import AuthorizationAction
from app.application.inventory_mutation import InventoryMutationService
from app.application.operation_recorder import OperationRecorder
from app.application.state_machine import assert_transition_allowed, can_transition
from app.application.time import utc_now
from app.domain.enums import OperationState, OperationType, SessionStatus, SessionType
from app.hardware import HardwareFacade
from app.hardware.dto import DrumPositionResult
from app.hardware.exceptions import HardwareError
from app.persistence.models import Operation, OperationSession, Slot
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.operations import OperationRepository, OperationSessionRepository


@dataclass(slots=True)
class RefillOperationService:
    operation_repository: OperationRepository
    inventory_repository: InventoryRepository
    session_repository: OperationSessionRepository
    authorization_service: AuthorizationService
    _recorder: OperationRecorder = field(init=False, repr=False)
    _inventory_mutation: InventoryMutationService = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._recorder = OperationRecorder(self.operation_repository)
        self._inventory_mutation = InventoryMutationService(self.inventory_repository)

    def validate_request(self, request: RefillRequest) -> OperationValidationResult:
        if request.quantity < 0:
            raise ValidationError("quantity must be non-negative")
        return OperationValidationResult(
            operation_type=OperationType.REFILL_ITEM,
            valid=True,
            messages=(),
        )

    def create_operation(self, command: CreateOperationCommand) -> OperationDTO:
        operation = self._build_operation(command)
        self.operation_repository.add(operation)
        return self._to_dto(operation)

    def execute(self, request: RefillRequest, hardware_facade: HardwareFacade) -> OperationDTO:
        self.authorization_service.require(
            AuthorizationRequest(
                action=AuthorizationAction.REFILL_EXECUTION,
                actor_user_id=request.operator_user_id,
            )
        )
        validation = self.validate_request(request)
        if not validation.valid:
            raise ValidationError("; ".join(validation.messages))

        slot = self._require_slot(request.slot_id)
        session = self._ensure_session(request)
        command = CreateOperationCommand(
            operation_type=OperationType.REFILL_ITEM,
            session_id=session.id,
            user_id=request.operator_user_id,
            item_id=request.item_id,
            slot_id=request.slot_id,
            qty_requested=request.quantity,
            operation_state=OperationState.CREATED,
            business_context={
                "requested_quantity": request.quantity,
                "mode": request.mode,
                "service_session_id": session.id,
            },
            hardware_context=self._slot_hardware_context(slot),
        )
        operation = self._recorder.create_operation(
            self._build_operation(command),
            comment="Refill operation created",
            context={"requested_quantity": request.quantity, "mode": request.mode, "service_session_id": session.id},
        )

        try:
            self._transition(operation, OperationState.AUTHORIZED, "Refill authorized")
            self._transition(operation, OperationState.SERVICE_MODE_REQUESTED, "Service mode requested")
            session.status = SessionStatus.ACTIVE
            self._transition(operation, OperationState.SERVICE_MODE_ACTIVE, "Service mode active")
            self._transition(operation, OperationState.AWAITING_SLOT_SELECTION, "Awaiting slot selection")
            self._transition(
                operation,
                OperationState.SLOT_SELECTED,
                "Refill slot selected",
                business_context={"selected_slot_id": slot.id},
            )

            self._transition(operation, OperationState.POSITIONING_REQUESTED, "Drum positioning requested")
            move_result = hardware_facade.move_drum_to_position(slot.drum_position)
            self._record_positioning_success(operation, move_result)

            self._transition(operation, OperationState.AWAITING_QTY_INPUT, "Awaiting refill quantity input")
            self._transition(
                operation,
                OperationState.QTY_ENTERED,
                "Refill quantity entered",
                business_context={"entered_quantity": request.quantity, "mode": request.mode},
            )
            self._transition(operation, OperationState.BALANCE_UPDATE_PENDING, "Refill balance update pending")
            balance = self._inventory_mutation.apply_refill(operation, request.quantity, request.mode)
            self._transition(
                operation,
                OperationState.BALANCE_UPDATED,
                "Refill balance updated",
                business_context={"inventory_quantity_after": balance.quantity},
            )
            self._transition(operation, OperationState.AWAITING_NEXT_ACTION, "Awaiting next refill action")
            self._transition(operation, OperationState.SESSION_COMPLETION_REQUESTED, "Refill session completion requested")
            self._transition(
                operation,
                OperationState.SESSION_FINALIZATION_IN_PROGRESS,
                "Refill session finalization in progress",
            )
            session.status = SessionStatus.COMPLETED
            session.finished_at = utc_now()
            self._transition(
                operation,
                OperationState.SESSION_COMPLETED,
                "Refill session completed",
                result="completed",
                qty_confirmed=request.quantity,
                finished=True,
            )
            self.operation_repository.session.commit()
        except HardwareError as error:
            session.status = SessionStatus.FAILED
            session.finished_at = datetime.utcnow()
            self._handle_hardware_error(operation, error)
        except Exception:
            self.operation_repository.session.rollback()
            raise

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

    def _transition(
        self,
        operation: Operation,
        target_state: OperationState,
        comment: str,
        *,
        hardware_context: dict[str, object] | None = None,
        business_context: dict[str, object] | None = None,
        result: str | None = None,
        qty_confirmed: int | None = None,
        finished: bool = False,
    ) -> None:
        self._recorder.transition(
            operation,
            target_state,
            comment=comment,
            history_context={**dict(hardware_context or {}), **dict(business_context or {})},
            hardware_context=hardware_context,
            business_context=business_context,
            result=result,
            qty_confirmed=qty_confirmed,
            finished=finished,
        )

    def _record_positioning_success(self, operation: Operation, result: DrumPositionResult) -> None:
        context = {
            "drum_move": {
                "device_type": result.device_type.value,
                "status": result.status.value,
                "ok": result.ok,
                "position": result.position,
            }
        }
        self._transition(
            operation,
            OperationState.POSITIONING_ACKNOWLEDGED,
            "Drum positioning acknowledged",
            hardware_context=context,
        )
        self._transition(operation, OperationState.POSITIONING_IN_PROGRESS, "Drum positioning in progress")
        self._transition(operation, OperationState.POSITIONING_COMPLETED, "Drum positioning completed")

    def _handle_hardware_error(self, operation: Operation, error: HardwareError) -> None:
        self._recorder.record_hardware_failure(
            operation,
            error,
            recovery_required=operation.operation_state in {
                OperationState.POSITIONING_COMPLETED,
                OperationState.BALANCE_UPDATE_PENDING,
                OperationState.BALANCE_UPDATED,
                OperationState.AWAITING_NEXT_ACTION,
            },
            comment="Refill hardware failure",
        )
        self.operation_repository.session.commit()

    def _ensure_session(self, request: RefillRequest) -> OperationSession:
        if request.session_id is not None:
            session = self.session_repository.get_by_id(request.session_id)
            if session is None:
                raise NotFoundError(f"Operation session not found: {request.session_id}")
            return session
        session = OperationSession(
            session_type=SessionType.REFILL,
            status=SessionStatus.CREATED,
            started_by_user_id=request.operator_user_id,
            started_at=utc_now(),
            finished_at=None,
            comment="Created by refill orchestration",
            context_json={"mode": request.mode},
        )
        self.session_repository.add(session)
        self.operation_repository.session.flush()
        return session

    def _require_slot(self, slot_id: int) -> Slot:
        slot = self.inventory_repository.get_slot(slot_id)
        if slot is None:
            raise NotFoundError(f"Slot not found: {slot_id}")
        return slot

    @staticmethod
    def _slot_hardware_context(slot: Slot) -> dict[str, object]:
        return {
            "slot": {
                "drum_position": slot.drum_position,
                "board_address": slot.board_address,
                "lock_number": slot.lock_number,
            }
        }

    @staticmethod
    def _build_operation(command: CreateOperationCommand) -> Operation:
        return Operation(
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
            started_at=utc_now(),
            finished_at=None,
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
