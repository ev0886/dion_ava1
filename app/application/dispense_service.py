from __future__ import annotations

from dataclasses import dataclass, field
from app.application.dto.operations import (
    CreateOperationCommand,
    DispenseRequest,
    OperationContextDTO,
    OperationDTO,
    OperationValidationResult,
    TransitionCheckResult,
)
from app.application.exceptions import NotFoundError, ValidationError
from app.application.inventory_mutation import InventoryMutationService
from app.application.operation_recorder import OperationRecorder
from app.application.state_machine import assert_transition_allowed, can_transition
from app.application.time import utc_now
from app.domain.enums import OperationState, OperationType
from app.hardware import HardwareFacade, UnlockResult
from app.hardware.dto import DrumPositionResult
from app.hardware.exceptions import HardwareError
from app.persistence.models import Operation, Slot
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.operations import OperationRepository


@dataclass(slots=True)
class DispenseOperationService:
    operation_repository: OperationRepository
    inventory_repository: InventoryRepository
    _recorder: OperationRecorder = field(init=False, repr=False)
    _inventory_mutation: InventoryMutationService = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._recorder = OperationRecorder(self.operation_repository)
        self._inventory_mutation = InventoryMutationService(self.inventory_repository)

    def validate_request(self, request: DispenseRequest) -> OperationValidationResult:
        if request.quantity <= 0:
            raise ValidationError("quantity must be positive")

        messages: list[str] = []
        balance = self.inventory_repository.get_balance(request.slot_id, request.item_id)
        if balance is None:
            messages.append("No inventory balance found for slot/item")
        elif balance.quantity < request.quantity:
            messages.append("Requested quantity exceeds current balance")
        if not self.inventory_repository.has_active_dispense_path(request.slot_id, request.item_id):
            messages.append("Slot/item path is not active for dispense")

        return OperationValidationResult(
            operation_type=OperationType.DISPENSE,
            valid=not messages,
            messages=tuple(messages),
        )

    def create_operation(self, command: CreateOperationCommand) -> OperationDTO:
        operation = self._build_operation(command)
        self.operation_repository.add(operation)
        return self._to_dto(operation)

    def execute(self, request: DispenseRequest, hardware_facade: HardwareFacade) -> OperationDTO:
        validation = self.validate_request(request)
        if not validation.valid:
            raise ValidationError("; ".join(validation.messages))

        slot = self._require_slot(request.slot_id)
        command = CreateOperationCommand(
            operation_type=OperationType.DISPENSE,
            session_id=request.session_id,
            user_id=request.user_id,
            item_id=request.item_id,
            slot_id=request.slot_id,
            qty_requested=request.quantity,
            operation_state=OperationState.CREATED,
            business_context={"requested_quantity": request.quantity},
            hardware_context=self._slot_hardware_context(slot),
        )
        operation = self._recorder.create_operation(
            self._build_operation(command),
            comment="Dispense operation created",
            context={"requested_quantity": request.quantity},
        )

        try:
            self._transition(operation, OperationState.AUTHORIZED, "Dispense authorized")
            self._transition(operation, OperationState.VALIDATION_IN_PROGRESS, "Dispense validation started")
            self._transition(operation, OperationState.VALIDATED, "Dispense validated")
            self._transition(operation, OperationState.QUEUED_FOR_EXECUTION, "Dispense queued for execution")

            self._transition(operation, OperationState.POSITIONING_REQUESTED, "Drum positioning requested")
            move_result = hardware_facade.move_drum_to_position(slot.drum_position)
            self._record_positioning_success(operation, move_result)

            self._transition(operation, OperationState.UNLOCK_REQUESTED, "Slot unlock requested")
            unlock_result = hardware_facade.unlock_lock(slot.board_address, slot.lock_number)
            self._record_unlock_success(operation, unlock_result)

            self._transition(operation, OperationState.USER_ACTION_PENDING, "Awaiting user dispense action")
            self._transition(operation, OperationState.COMPLETION_VERIFICATION, "Dispense completion verified")
            self._transition(operation, OperationState.INVENTORY_WRITE_PENDING, "Dispense inventory write pending")
            balance = self._inventory_mutation.apply_dispense(operation, request.quantity)
            self._transition(
                operation,
                OperationState.INVENTORY_WRITTEN,
                "Dispense inventory written",
                business_context={"inventory_quantity_after": balance.quantity},
            )
            self._transition(
                operation,
                OperationState.COMPLETED,
                "Dispense completed",
                result="completed",
                qty_confirmed=request.quantity,
                finished=True,
            )
            self.operation_repository.session.commit()
        except HardwareError as error:
            self._handle_hardware_error(operation, error)
        except Exception:
            self.operation_repository.session.rollback()
            raise

        return self._to_dto(operation)

    def assert_transition_allowed(self, current_state: OperationState, target_state: OperationState) -> None:
        assert_transition_allowed(OperationType.DISPENSE, current_state, target_state)

    def check_transition(self, current_state: OperationState, target_state: OperationState) -> TransitionCheckResult:
        return TransitionCheckResult(
            operation_type=OperationType.DISPENSE,
            current_state=current_state,
            target_state=target_state,
            allowed=can_transition(OperationType.DISPENSE, current_state, target_state),
        )

    def build_operation_context(self, request: DispenseRequest) -> OperationContextDTO:
        return OperationContextDTO(
            operation_type=OperationType.DISPENSE,
            user_id=request.user_id,
            item_id=request.item_id,
            slot_id=request.slot_id,
            session_id=request.session_id,
            operation_state=OperationState.CREATED,
            business_context={"requested_quantity": request.quantity},
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

    def _record_unlock_success(self, operation: Operation, result: UnlockResult) -> None:
        context = {
            "unlock": {
                "device_type": result.device_type.value,
                "status": result.status.value,
                "ok": result.ok,
                "board_address": result.board_address,
                "lock_number": result.lock_number,
                "lock_state": result.lock_state.value,
            }
        }
        self._transition(
            operation,
            OperationState.UNLOCK_ACKNOWLEDGED,
            "Slot unlock acknowledged",
            hardware_context=context,
        )
        self._transition(operation, OperationState.UNLOCK_COMPLETED, "Slot unlock completed")

    def _handle_hardware_error(self, operation: Operation, error: HardwareError) -> None:
        self._recorder.record_hardware_failure(
            operation,
            error,
            recovery_required=operation.operation_state in {
                OperationState.POSITIONING_COMPLETED,
                OperationState.UNLOCK_REQUESTED,
                OperationState.UNLOCK_ACKNOWLEDGED,
                OperationState.UNLOCK_COMPLETED,
                OperationState.USER_ACTION_PENDING,
                OperationState.COMPLETION_VERIFICATION,
                OperationState.INVENTORY_WRITE_PENDING,
                OperationState.INVENTORY_WRITTEN,
            },
            comment="Dispense hardware failure",
        )
        self.operation_repository.session.commit()

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
            operation_type=OperationType.DISPENSE,
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
