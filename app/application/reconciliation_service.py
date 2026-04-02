from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.recovery import ReconciliationResultDTO
from app.domain.enums import OperationState, OperationType
from app.persistence.models import Operation
from app.persistence.repositories.inventory import InventoryRepository


@dataclass(slots=True)
class RecoveryReconciliationService:
    inventory_repository: InventoryRepository

    def reconcile_operation(self, operation: Operation) -> ReconciliationResultDTO:
        transactions = tuple(self.inventory_repository.list_transactions(operation_id=operation.id))
        inventory_transaction_ids = tuple(transaction.id for transaction in transactions if transaction.id is not None)
        has_inventory_transaction = bool(transactions)
        pending_state, written_state = self._inventory_checkpoint_states(operation.operation_type)

        if operation.operation_state is written_state and has_inventory_transaction:
            outcome = "no_action_needed"
            reason = "Inventory mutation evidence already exists for the unfinished operation."
        elif operation.operation_state in {pending_state, written_state} and not has_inventory_transaction:
            outcome = "inventory_write_likely_missing"
            reason = "The operation reached its inventory mutation stage without a recorded inventory transaction."
        elif not has_inventory_transaction and self._is_before_inventory_mutation(operation.operation_type, operation.operation_state):
            outcome = "operation_likely_failed_before_inventory_mutation"
            reason = "No inventory transaction was recorded before the operation stopped before its mutation stage."
        else:
            outcome = "manual_review_required"
            reason = "The available operation and inventory evidence is insufficient for a stronger conclusion."

        return ReconciliationResultDTO(
            operation_id=operation.id or 0,
            operation_state=operation.operation_state.value,
            inventory_transaction_count=len(transactions),
            inventory_transaction_ids=inventory_transaction_ids,
            outcome=outcome,
            reason=reason,
        )

    @staticmethod
    def _inventory_checkpoint_states(operation_type: OperationType) -> tuple[OperationState, OperationState]:
        if operation_type is OperationType.REFILL_ITEM:
            return (OperationState.BALANCE_UPDATE_PENDING, OperationState.BALANCE_UPDATED)
        return (OperationState.INVENTORY_WRITE_PENDING, OperationState.INVENTORY_WRITTEN)

    def _is_before_inventory_mutation(self, operation_type: OperationType, state: OperationState) -> bool:
        pending_state, _ = self._inventory_checkpoint_states(operation_type)
        sequence = self._operation_sequence(operation_type)
        if state not in sequence:
            return False
        return sequence.index(state) < sequence.index(pending_state)

    @staticmethod
    def _operation_sequence(operation_type: OperationType) -> tuple[OperationState, ...]:
        if operation_type is OperationType.DISPENSE:
            return (
                OperationState.CREATED,
                OperationState.AUTHORIZED,
                OperationState.VALIDATION_IN_PROGRESS,
                OperationState.VALIDATED,
                OperationState.QUEUED_FOR_EXECUTION,
                OperationState.POSITIONING_REQUESTED,
                OperationState.POSITIONING_ACKNOWLEDGED,
                OperationState.POSITIONING_IN_PROGRESS,
                OperationState.POSITIONING_COMPLETED,
                OperationState.UNLOCK_REQUESTED,
                OperationState.UNLOCK_ACKNOWLEDGED,
                OperationState.UNLOCK_COMPLETED,
                OperationState.USER_ACTION_PENDING,
                OperationState.COMPLETION_VERIFICATION,
                OperationState.INVENTORY_WRITE_PENDING,
                OperationState.INVENTORY_WRITTEN,
                OperationState.COMPLETED,
            )
        if operation_type is OperationType.RETURN:
            return (
                OperationState.CREATED,
                OperationState.AUTHORIZED,
                OperationState.RETURN_RULES_VALIDATION,
                OperationState.RETURN_SLOT_RESOLUTION_IN_PROGRESS,
                OperationState.RETURN_SLOT_RESOLVED,
                OperationState.VALIDATED,
                OperationState.QUEUED_FOR_EXECUTION,
                OperationState.POSITIONING_REQUESTED,
                OperationState.POSITIONING_ACKNOWLEDGED,
                OperationState.POSITIONING_IN_PROGRESS,
                OperationState.POSITIONING_COMPLETED,
                OperationState.UNLOCK_REQUESTED,
                OperationState.UNLOCK_ACKNOWLEDGED,
                OperationState.UNLOCK_COMPLETED,
                OperationState.USER_ACTION_PENDING,
                OperationState.COMPLETION_VERIFICATION,
                OperationState.INVENTORY_WRITE_PENDING,
                OperationState.INVENTORY_WRITTEN,
                OperationState.COMPLETED,
            )
        return (
            OperationState.CREATED,
            OperationState.AUTHORIZED,
            OperationState.SERVICE_MODE_REQUESTED,
            OperationState.SERVICE_MODE_ACTIVE,
            OperationState.AWAITING_SLOT_SELECTION,
            OperationState.SLOT_SELECTED,
            OperationState.POSITIONING_REQUESTED,
            OperationState.POSITIONING_ACKNOWLEDGED,
            OperationState.POSITIONING_IN_PROGRESS,
            OperationState.POSITIONING_COMPLETED,
            OperationState.AWAITING_QTY_INPUT,
            OperationState.QTY_ENTERED,
            OperationState.BALANCE_UPDATE_PENDING,
            OperationState.BALANCE_UPDATED,
            OperationState.AWAITING_NEXT_ACTION,
            OperationState.SESSION_COMPLETION_REQUESTED,
            OperationState.SESSION_FINALIZATION_IN_PROGRESS,
            OperationState.SESSION_COMPLETED,
        )
