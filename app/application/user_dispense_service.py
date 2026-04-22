from __future__ import annotations

from dataclasses import dataclass, field

from app.application.dispense_service import DispenseOperationService
from app.application.dto.inventory import UserDispenseOptionDTO, UserDispenseOptionsResult
from app.application.dto.operations import DispenseRequest, OperationDTO
from app.application.exceptions import NotFoundError, ValidationError
from app.application.operation_recorder import OperationRecorder
from app.application.time import utc_now
from app.domain.enums import InventoryTransactionType, OperationState, OperationType
from app.persistence.models import EventLog, InventoryTransaction, Operation
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import EventLogRepository
from app.persistence.repositories.operations import OperationRepository


@dataclass(slots=True)
class UserDispenseService:
    operation_repository: OperationRepository
    inventory_repository: InventoryRepository
    event_log_repository: EventLogRepository
    _recorder: OperationRecorder = field(init=False, repr=False)
    _restriction_guard: DispenseOperationService = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._recorder = OperationRecorder(self.operation_repository)
        self._restriction_guard = DispenseOperationService(
            self.operation_repository,
            self.inventory_repository,
        )

    def list_options_for_user(self, user_id: int) -> UserDispenseOptionsResult:
        self._validate_user_id(user_id)

        try:
            self._restriction_guard._enforce_dispense_restriction(user_id)
        except ValidationError as error:
            return UserDispenseOptionsResult(
                options=(),
                restriction_blocked=True,
                unavailable_reason=str(error),
            )

        aggregated: dict[int, UserDispenseOptionDTO] = {}
        for option in self.inventory_repository.list_available_dispense_options():
            current = aggregated.get(option.item_id)
            if current is None:
                aggregated[option.item_id] = UserDispenseOptionDTO(
                    item_id=option.item_id,
                    item_name=option.item_name,
                    item_unit=option.item_unit,
                    total_quantity=option.quantity,
                )
                continue
            aggregated[option.item_id] = UserDispenseOptionDTO(
                item_id=current.item_id,
                item_name=current.item_name,
                item_unit=current.item_unit,
                total_quantity=current.total_quantity + option.quantity,
            )

        return UserDispenseOptionsResult(options=tuple(aggregated.values()))

    def dispense_without_hardware(self, request: DispenseRequest) -> OperationDTO:
        self._validate_request(request)
        self._restriction_guard._enforce_dispense_restriction(request.user_id)

        resolved_option = self.inventory_repository.resolve_available_dispense_option(request.item_id)
        if resolved_option is None:
            raise NotFoundError(f"No available dispense slot found for item: {request.item_id}")
        if not self.inventory_repository.has_active_dispense_path(resolved_option.slot_id, resolved_option.item_id):
            raise ValidationError("Slot/item path is not active for dispense")

        operation = Operation(
            session_id=request.session_id,
            operation_type=OperationType.DISPENSE,
            operation_state=OperationState.CREATED,
            user_id=request.user_id,
            item_id=request.item_id,
            slot_id=resolved_option.slot_id,
            qty_requested=1,
            qty_confirmed=None,
            result=None,
            error_code=None,
            error_message=None,
            hardware_context_json={},
            business_context_json={
                "source": "user_touch",
                "execution_mode": "real_db_no_hardware",
                "selected_item_id": request.item_id,
                "resolved_slot_id": resolved_option.slot_id,
                "single_slot_single_item_model": True,
            },
            started_at=utc_now(),
            finished_at=None,
        )
        self._recorder.create_operation(
            operation,
            comment="User dispense created without hardware execution",
            context={
                "source": "user_touch",
                "execution_mode": "real_db_no_hardware",
                "selected_item_id": request.item_id,
                "resolved_slot_id": resolved_option.slot_id,
            },
        )

        try:
            clear_quantity = self._require_positive_balance_quantity(resolved_option.slot_id, resolved_option.item_id)
            self._transition(operation, OperationState.AUTHORIZED, "User dispense authorized")
            self._transition(operation, OperationState.VALIDATION_IN_PROGRESS, "User dispense validation started")
            self._transition(operation, OperationState.VALIDATED, "User dispense validated")
            self._transition(
                operation,
                OperationState.QUEUED_FOR_EXECUTION,
                "User dispense queued for DB-only completion",
                business_context={"execution_mode": "real_db_no_hardware"},
            )
            self._transition(
                operation,
                OperationState.POSITIONING_REQUESTED,
                "Hardware positioning skipped for DB-only user dispense",
            )
            self._transition(
                operation,
                OperationState.POSITIONING_ACKNOWLEDGED,
                "Hardware positioning acknowledged as skipped",
            )
            self._transition(
                operation,
                OperationState.POSITIONING_IN_PROGRESS,
                "Hardware positioning marked in progress as skipped",
            )
            self._transition(
                operation,
                OperationState.POSITIONING_COMPLETED,
                "Hardware positioning marked completed without actuation",
            )
            self._transition(
                operation,
                OperationState.UNLOCK_REQUESTED,
                "Slot unlock skipped for DB-only user dispense",
            )
            self._transition(
                operation,
                OperationState.UNLOCK_ACKNOWLEDGED,
                "Slot unlock acknowledged as skipped",
            )
            self._transition(
                operation,
                OperationState.UNLOCK_COMPLETED,
                "Slot unlock marked completed without actuation",
            )
            self._transition(
                operation,
                OperationState.USER_ACTION_PENDING,
                "User dispense shell continued without hardware actuation",
            )
            self._transition(
                operation,
                OperationState.COMPLETION_VERIFICATION,
                "User dispense DB-only completion verified",
            )
            self._transition(
                operation,
                OperationState.INVENTORY_WRITE_PENDING,
                "User dispense inventory write pending",
            )
            self._clear_slot_inventory(
                operation=operation,
                slot_id=resolved_option.slot_id,
                item_id=resolved_option.item_id,
                quantity_before=clear_quantity,
            )
            self._transition(
                operation,
                OperationState.INVENTORY_WRITTEN,
                "User dispense inventory written",
                business_context={
                    "inventory_quantity_after": 0,
                    "cleared_slot": True,
                    "cleared_quantity": clear_quantity,
                },
            )
            self.event_log_repository.add(
                EventLog(
                    event_type="user_dispense_no_hardware",
                    level="info",
                    source="user_touch",
                    operation_id=operation.id,
                    session_id=operation.session_id,
                    user_id=operation.user_id,
                    slot_id=operation.slot_id,
                    item_id=operation.item_id,
                    qty=1,
                    result="success",
                    comment="User dispense completed without hardware execution",
                    message="User dispense committed in DB-only mode",
                    payload_json={
                        "execution_mode": "real_db_no_hardware",
                        "cleared_slot": True,
                        "cleared_quantity": clear_quantity,
                    },
                )
            )
            self._transition(
                operation,
                OperationState.COMPLETED,
                "User dispense completed without hardware execution",
                result="completed",
                qty_confirmed=1,
                finished=True,
            )
            self.operation_repository.session.commit()
        except Exception:
            self.operation_repository.session.rollback()
            raise

        return self._to_dto(operation)

    def _clear_slot_inventory(
        self,
        *,
        operation: Operation,
        slot_id: int,
        item_id: int,
        quantity_before: int,
    ) -> None:
        balance = self.inventory_repository.get_balance(slot_id, item_id)
        if balance is None or balance.quantity <= 0:
            raise ValidationError("No inventory balance found for slot/item")
        balance.quantity = 0
        self.inventory_repository.add_transaction(
            InventoryTransaction(
                slot_id=slot_id,
                item_id=item_id,
                operation_id=operation.id,
                session_id=operation.session_id,
                transaction_type=InventoryTransactionType.DISPENSE_DEBIT,
                quantity_delta=-quantity_before,
                quantity_before=quantity_before,
                quantity_after=0,
                comment="User dispense inventory committed via DB-only flow",
                created_at=utc_now(),
            )
        )
        self.inventory_repository.session.flush()

    def _transition(
        self,
        operation: Operation,
        target_state: OperationState,
        comment: str,
        *,
        business_context: dict[str, object] | None = None,
        result: str | None = None,
        qty_confirmed: int | None = None,
        finished: bool = False,
    ) -> None:
        self._recorder.transition(
            operation,
            target_state,
            comment=comment,
            history_context=dict(business_context or {}),
            business_context=business_context,
            result=result,
            qty_confirmed=qty_confirmed,
            finished=finished,
        )

    def _require_positive_balance_quantity(self, slot_id: int, item_id: int) -> int:
        balance = self.inventory_repository.get_balance(slot_id, item_id)
        if balance is None or balance.quantity <= 0:
            raise ValidationError("No available dispense slot found for selected item")
        return balance.quantity

    @staticmethod
    def _validate_request(request: DispenseRequest) -> None:
        if request.user_id <= 0:
            raise ValidationError("user_id must be positive")
        if request.item_id <= 0:
            raise ValidationError("item_id must be positive")
        if request.quantity != 1:
            raise ValidationError("quantity must be exactly 1 for user DB-only dispense")

    @staticmethod
    def _validate_user_id(user_id: int) -> None:
        if user_id <= 0:
            raise ValidationError("user_id must be positive")

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
