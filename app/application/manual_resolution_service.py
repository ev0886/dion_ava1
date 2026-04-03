from __future__ import annotations

from dataclasses import dataclass, field

from app.application.dto.recovery import (
    AffectedInventoryOutcomeDTO,
    AffectedOperationOutcomeDTO,
    InventoryCorrectionRequestDTO,
    ManualRecoveryActionRequestDTO,
    ManualResolutionPreparationDTO,
    RecoveryActionDTO,
    RecoveryCaseEntityDTO,
    RecoveryResolutionResultDTO,
)
from app.application.exceptions import RecoveryError, ValidationError
from app.application.operation_recorder import OperationRecorder
from app.application.time import utc_now
from app.domain.enums import InventoryTransactionType, OperationState, OperationType, RecoveryActionStatus, RecoveryStatus
from app.persistence.models import AuditLog, EventLog, InventoryBalance, InventoryTransaction, Operation, RecoveryAction
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository


@dataclass(slots=True)
class ManualResolutionPreparationService:
    recovery_repository: RecoveryRepository

    def prepare_case(self, recovery_case_id: int) -> ManualResolutionPreparationDTO:
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            raise RecoveryError(f"Recovery case not found: {recovery_case_id}")

        entities = tuple(
            RecoveryCaseEntityDTO(
                entity_type=entity.entity_type,
                entity_id=entity.entity_id,
                role=entity.role,
                decision_outcome=entity.decision_outcome,
            )
            for entity in self.recovery_repository.list_entities_for_case(recovery_case_id)
        )
        actions = tuple(
            RecoveryActionDTO(
                action_type=action.action_type,
                status=action.status.value,
                comment=action.comment,
                context=dict(action.context_json or {}),
                created_at=action.created_at,
            )
            for action in self.recovery_repository.list_actions_for_case(recovery_case_id)
        )
        return ManualResolutionPreparationDTO(
            recovery_case_id=recovery_case.id,
            classification=recovery_case.classification,
            status=recovery_case.status,
            summary=recovery_case.summary,
            impacted_entities=entities,
            recovery_actions=actions,
            recommended_next_action_categories=self._recommend_categories(dict(recovery_case.context_json or {})),
            context=dict(recovery_case.context_json or {}),
        )

    @staticmethod
    def _recommend_categories(context: dict[str, object]) -> tuple[str, ...]:
        outcome = context.get("reconciliation_outcome")
        if outcome == "inventory_write_likely_missing":
            return (
                "review_operation_history",
                "verify_inventory_records",
                "confirm_physical_state",
            )
        if outcome == "no_action_needed":
            return (
                "review_operation_history",
                "decide_case_closure",
            )
        return (
            "review_operation_history",
            "verify_inventory_records",
            "confirm_physical_state",
            "decide_case_closure",
        )


@dataclass(slots=True)
class ManualRecoveryActionService:
    recovery_repository: RecoveryRepository
    operation_repository: OperationRepository
    inventory_repository: InventoryRepository
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository
    _operation_recorder: OperationRecorder = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._operation_recorder = OperationRecorder(self.operation_repository)

    def apply_action(self, request: ManualRecoveryActionRequestDTO) -> RecoveryResolutionResultDTO:
        recovery_case = self._require_open_case(request.recovery_case_id)
        operation = self._get_linked_operation(recovery_case.id)
        before_case = self._case_snapshot(recovery_case)

        affected_operation: AffectedOperationOutcomeDTO | None = None
        affected_inventory: AffectedInventoryOutcomeDTO | None = None

        if request.action == "confirm_operation_succeeded":
            affected_operation = self._confirm_operation_succeeded(recovery_case.id, operation, request.comment)
            recovery_case.status = RecoveryStatus.IN_PROGRESS
            summary_message = f"Recovery case {recovery_case.id} recorded manual success confirmation."
        elif request.action == "confirm_operation_failed":
            affected_operation = self._confirm_operation_failed(recovery_case.id, operation, request.comment)
            recovery_case.status = RecoveryStatus.IN_PROGRESS
            summary_message = f"Recovery case {recovery_case.id} recorded manual failure confirmation."
        elif request.action == "apply_inventory_correction":
            correction = request.inventory_correction
            if correction is None:
                raise ValidationError("inventory_correction is required for apply_inventory_correction")
            affected_inventory = self._apply_inventory_correction(recovery_case.id, operation, correction, request.comment)
            recovery_case.status = RecoveryStatus.IN_PROGRESS
            summary_message = f"Recovery case {recovery_case.id} recorded manual inventory correction."
        elif request.action == "mark_no_action_needed":
            resolution_code = request.resolution_code or "no_action_needed"
            self._close_case(
                recovery_case,
                resolution_code=resolution_code,
                comment=request.comment,
                action=request.action,
            )
            summary_message = f"Recovery case {recovery_case.id} was closed with no further action."
        elif request.action == "close_recovery_case":
            raise ValidationError("close_recovery_case must use the resolve recovery workflow")
        else:
            raise ValidationError(f"Unsupported recovery action: {request.action}")

        result = RecoveryResolutionResultDTO(
            recovery_case_id=recovery_case.id,
            action_applied=request.action,
            case_status=recovery_case.status,
            case_resolved=recovery_case.resolved_at is not None,
            resolution_code=self._resolution_code(recovery_case),
            affected_operation=affected_operation,
            affected_inventory=affected_inventory,
            summary_message=summary_message,
        )
        self._record_action_row(recovery_case.id, request, result)
        self._record_audit(
            recovery_case_id=recovery_case.id,
            actor_user_id=request.actor_user_id,
            action=request.action,
            comment=request.comment,
            before_case=before_case,
            after_case=self._case_snapshot(recovery_case),
            affected_operation=affected_operation,
            affected_inventory=affected_inventory,
            resolution_code=result.resolution_code,
        )
        if result.case_resolved:
            self._record_event(
                recovery_case_id=recovery_case.id,
                operation=operation,
                actor_user_id=request.actor_user_id,
                action=request.action,
                result="resolved",
                comment=request.comment,
                resolution_code=result.resolution_code,
            )
        self.recovery_repository.session.commit()
        return result

    def resolve_case(self, request: ManualRecoveryActionRequestDTO) -> RecoveryResolutionResultDTO:
        recovery_case = self._require_open_case(request.recovery_case_id)
        before_case = self._case_snapshot(recovery_case)
        operation = self._get_linked_operation(recovery_case.id, required=False)

        if request.action not in {"mark_no_action_needed", "close_recovery_case"}:
            raise ValidationError("resolve workflow only supports mark_no_action_needed or close_recovery_case")
        if not request.resolution_code:
            raise ValidationError("resolution_code is required to resolve a recovery case")

        self._close_case(
            recovery_case,
            resolution_code=request.resolution_code,
            comment=request.comment,
            action=request.action,
        )
        result = RecoveryResolutionResultDTO(
            recovery_case_id=recovery_case.id,
            action_applied=request.action,
            case_status=recovery_case.status,
            case_resolved=True,
            resolution_code=request.resolution_code,
            affected_operation=self._current_operation_outcome(operation) if operation is not None else None,
            affected_inventory=None,
            summary_message=f"Recovery case {recovery_case.id} was resolved with {request.resolution_code}.",
        )
        self._record_action_row(recovery_case.id, request, result)
        self._record_audit(
            recovery_case_id=recovery_case.id,
            actor_user_id=request.actor_user_id,
            action=request.action,
            comment=request.comment,
            before_case=before_case,
            after_case=self._case_snapshot(recovery_case),
            affected_operation=result.affected_operation,
            affected_inventory=None,
            resolution_code=request.resolution_code,
        )
        self._record_event(
            recovery_case_id=recovery_case.id,
            operation=operation,
            actor_user_id=request.actor_user_id,
            action=request.action,
            result="resolved",
            comment=request.comment,
            resolution_code=request.resolution_code,
        )
        self.recovery_repository.session.commit()
        return result

    def _require_open_case(self, recovery_case_id: int):
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            raise RecoveryError(f"Recovery case not found: {recovery_case_id}")
        if recovery_case.resolved_at is not None or recovery_case.status is RecoveryStatus.RESOLVED:
            raise RecoveryError(f"Recovery case is already resolved: {recovery_case_id}")
        if recovery_case.status not in {RecoveryStatus.OPEN, RecoveryStatus.IN_PROGRESS}:
            raise RecoveryError(f"Recovery case is not open for manual action: {recovery_case_id}")
        return recovery_case

    def _get_linked_operation(self, recovery_case_id: int, *, required: bool = True) -> Operation | None:
        primary_entity = self.recovery_repository.get_case_entity(
            recovery_case_id,
            entity_type="operation",
            entity_id=self._primary_operation_entity_id(recovery_case_id),
            role="primary_operation",
        )
        if primary_entity is None:
            if required:
                raise RecoveryError(f"Recovery case {recovery_case_id} is missing linked operation evidence")
            return None
        operation = self.operation_repository.get_by_id(int(primary_entity.entity_id))
        if operation is None and required:
            raise RecoveryError(f"Linked operation not found for recovery case {recovery_case_id}")
        return operation

    def _primary_operation_entity_id(self, recovery_case_id: int) -> str:
        for entity in self.recovery_repository.list_entities_for_case(recovery_case_id):
            if entity.entity_type == "operation" and entity.role == "primary_operation":
                return entity.entity_id
        raise RecoveryError(f"Recovery case {recovery_case_id} is missing linked operation evidence")

    def _confirm_operation_succeeded(
        self,
        recovery_case_id: int,
        operation: Operation | None,
        comment: str | None,
    ) -> AffectedOperationOutcomeDTO:
        operation = self._require_operation(operation, recovery_case_id)
        if not self._operation_success_is_supported(recovery_case_id, operation):
            raise RecoveryError(
                "confirm_operation_succeeded is incompatible with the current evidence; "
                "inventory/result evidence is not strong enough for success confirmation"
            )
        target_state = self._success_terminal_state(operation.operation_type)
        qty_confirmed = operation.qty_confirmed if operation.qty_confirmed is not None else operation.qty_requested
        self._operation_recorder.recover_to_terminal(
            operation,
            target_state,
            comment=comment or "Operation manually confirmed as succeeded during recovery handling",
            history_context={"recovery_case_id": recovery_case_id, "manual_action": "confirm_operation_succeeded"},
            result="manually_confirmed_success",
            error_code=None,
            error_message=None,
            qty_confirmed=qty_confirmed,
            clear_error=True,
        )
        self._update_operation_entity_decision(recovery_case_id, "confirmed_succeeded")
        return AffectedOperationOutcomeDTO(
            operation_id=operation.id or 0,
            state=operation.operation_state.value,
            result=operation.result,
            changed=True,
            message="Operation moved to a successful terminal state.",
        )

    def _confirm_operation_failed(
        self,
        recovery_case_id: int,
        operation: Operation | None,
        comment: str | None,
    ) -> AffectedOperationOutcomeDTO:
        operation = self._require_operation(operation, recovery_case_id)
        if operation.operation_state in {
            OperationState.COMPLETED,
            OperationState.SESSION_COMPLETED,
            OperationState.DEGRADED_READY,
            OperationState.SYSTEM_READY,
        }:
            raise RecoveryError("confirm_operation_failed is incompatible with an already successful operation state")
        self._operation_recorder.recover_to_terminal(
            operation,
            OperationState.FAILED,
            comment=comment or "Operation manually confirmed as failed during recovery handling",
            history_context={"recovery_case_id": recovery_case_id, "manual_action": "confirm_operation_failed"},
            result="manually_confirmed_failure",
            error_code="manual_recovery_failure_confirmed",
            error_message=comment or "Failure was explicitly confirmed during recovery handling",
            qty_confirmed=0 if operation.qty_confirmed is None else operation.qty_confirmed,
        )
        self._update_operation_entity_decision(recovery_case_id, "confirmed_failed")
        return AffectedOperationOutcomeDTO(
            operation_id=operation.id or 0,
            state=operation.operation_state.value,
            result=operation.result,
            changed=True,
            message="Operation moved to a failed terminal state.",
        )

    def _apply_inventory_correction(
        self,
        recovery_case_id: int,
        operation: Operation | None,
        correction: InventoryCorrectionRequestDTO,
        comment: str | None,
    ) -> AffectedInventoryOutcomeDTO:
        if correction.slot_id <= 0 or correction.item_id <= 0:
            raise ValidationError("slot_id and item_id must be positive for inventory correction")
        balance = self.inventory_repository.get_balance(correction.slot_id, correction.item_id)
        if balance is None:
            balance = InventoryBalance(slot_id=correction.slot_id, item_id=correction.item_id, quantity=0)
            self.inventory_repository.add_balance(balance)
            self.inventory_repository.session.flush()
        quantity_before = balance.quantity
        quantity_after = quantity_before + correction.quantity_delta
        if quantity_after < 0:
            raise RecoveryError("Inventory correction would make the balance negative")
        balance.quantity = quantity_after
        transaction = InventoryTransaction(
            slot_id=correction.slot_id,
            item_id=correction.item_id,
            operation_id=operation.id if operation is not None else None,
            session_id=operation.session_id if operation is not None else None,
            transaction_type=InventoryTransactionType.RECOVERY_ADJUSTMENT,
            quantity_delta=correction.quantity_delta,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            comment=comment or "Manual recovery inventory correction applied",
            created_at=utc_now(),
        )
        self.inventory_repository.add_transaction(transaction)
        self.inventory_repository.session.flush()
        self._update_inventory_entity_decision(recovery_case_id, correction, "corrected")
        return AffectedInventoryOutcomeDTO(
            slot_id=correction.slot_id,
            item_id=correction.item_id,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            quantity_delta=correction.quantity_delta,
            transaction_type=InventoryTransactionType.RECOVERY_ADJUSTMENT.value,
            transaction_id=transaction.id,
            changed=True,
            message="Inventory correction was recorded.",
        )

    def _close_case(self, recovery_case, *, resolution_code: str, comment: str | None, action: str) -> None:
        context = dict(recovery_case.context_json or {})
        context["manual_resolution"] = {
            "resolution_code": resolution_code,
            "action": action,
            "resolved_at": utc_now().isoformat(),
            "comment": comment,
        }
        recovery_case.context_json = context
        recovery_case.status = RecoveryStatus.RESOLVED
        recovery_case.resolved_at = utc_now()

    def _record_action_row(
        self,
        recovery_case_id: int,
        request: ManualRecoveryActionRequestDTO,
        result: RecoveryResolutionResultDTO,
    ) -> None:
        self.recovery_repository.add_action(
            RecoveryAction(
                recovery_case_id=recovery_case_id,
                action_type=request.action,
                status=RecoveryActionStatus.APPLIED,
                applied_at=utc_now(),
                comment=request.comment,
                context_json={
                    "actor_user_id": request.actor_user_id,
                    "resolution_code": result.resolution_code,
                    "case_status": result.case_status.value,
                    "case_resolved": result.case_resolved,
                    "inventory_correction": (
                        {
                            "slot_id": request.inventory_correction.slot_id,
                            "item_id": request.inventory_correction.item_id,
                            "quantity_delta": request.inventory_correction.quantity_delta,
                        }
                        if request.inventory_correction is not None
                        else None
                    ),
                },
            )
        )

    def _record_audit(
        self,
        *,
        recovery_case_id: int,
        actor_user_id: int | None,
        action: str,
        comment: str | None,
        before_case: dict[str, object],
        after_case: dict[str, object],
        affected_operation: AffectedOperationOutcomeDTO | None,
        affected_inventory: AffectedInventoryOutcomeDTO | None,
        resolution_code: str | None,
    ) -> None:
        self.audit_log_repository.add(
            AuditLog(
                entity_type="recovery_case",
                entity_id=str(recovery_case_id),
                action=f"manual_recovery_{action}",
                actor_user_id=actor_user_id,
                reason_code=resolution_code,
                comment=comment,
                before_json=before_case,
                after_json={
                    **after_case,
                    "affected_operation": self._operation_outcome_json(affected_operation),
                    "affected_inventory": self._inventory_outcome_json(affected_inventory),
                },
            )
        )

    def _record_event(
        self,
        *,
        recovery_case_id: int,
        operation: Operation | None,
        actor_user_id: int | None,
        action: str,
        result: str,
        comment: str | None,
        resolution_code: str | None,
    ) -> None:
        self.event_log_repository.add(
            EventLog(
                event_type="recovery_case_resolved",
                level="info",
                source="manual_recovery_action_service",
                operation_id=operation.id if operation is not None else None,
                session_id=operation.session_id if operation is not None else None,
                user_id=actor_user_id,
                slot_id=operation.slot_id if operation is not None else None,
                item_id=operation.item_id if operation is not None else None,
                qty=operation.qty_confirmed if operation is not None else None,
                result=result,
                comment=comment,
                message=f"Recovery case {recovery_case_id} resolved",
                payload_json={
                    "recovery_case_id": recovery_case_id,
                    "action": action,
                    "resolution_code": resolution_code,
                },
            )
        )

    def _operation_success_is_supported(self, recovery_case_id: int, operation: Operation) -> bool:
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            return False
        context = dict(recovery_case.context_json or {})
        transaction_ids = context.get("inventory_transaction_ids")
        detected_state = context.get("detected_state")
        if context.get("reconciliation_outcome") != "no_action_needed":
            return False
        if not isinstance(transaction_ids, list) or len(transaction_ids) == 0:
            return False
        return detected_state in {
            OperationState.INVENTORY_WRITTEN.value,
            OperationState.BALANCE_UPDATED.value,
        }

    @staticmethod
    def _success_terminal_state(operation_type: OperationType) -> OperationState:
        if operation_type is OperationType.REFILL_ITEM:
            return OperationState.SESSION_COMPLETED
        return OperationState.COMPLETED

    @staticmethod
    def _require_operation(operation: Operation | None, recovery_case_id: int) -> Operation:
        if operation is None:
            raise RecoveryError(f"Linked operation not found for recovery case {recovery_case_id}")
        return operation

    def _update_operation_entity_decision(self, recovery_case_id: int, outcome: str) -> None:
        entity_id = self._primary_operation_entity_id(recovery_case_id)
        entity = self.recovery_repository.get_case_entity(
            recovery_case_id,
            entity_type="operation",
            entity_id=entity_id,
            role="primary_operation",
        )
        if entity is not None:
            entity.decision_outcome = outcome

    def _update_inventory_entity_decision(
        self,
        recovery_case_id: int,
        correction: InventoryCorrectionRequestDTO,
        outcome: str,
    ) -> None:
        entity = self.recovery_repository.get_case_entity(
            recovery_case_id,
            entity_type="inventory_balance",
            entity_id=f"slot:{correction.slot_id}:item:{correction.item_id}",
            role="inventory_snapshot_target",
        )
        if entity is not None:
            entity.decision_outcome = outcome

    @staticmethod
    def _case_snapshot(recovery_case) -> dict[str, object]:
        return {
            "status": recovery_case.status.value,
            "resolved_at": recovery_case.resolved_at.isoformat() if recovery_case.resolved_at is not None else None,
            "context": dict(recovery_case.context_json or {}),
        }

    @staticmethod
    def _resolution_code(recovery_case) -> str | None:
        resolution = dict(recovery_case.context_json or {}).get("manual_resolution")
        if isinstance(resolution, dict):
            value = resolution.get("resolution_code")
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _operation_outcome_json(
        outcome: AffectedOperationOutcomeDTO | None,
    ) -> dict[str, object] | None:
        if outcome is None:
            return None
        return {
            "operation_id": outcome.operation_id,
            "state": outcome.state,
            "result": outcome.result,
            "changed": outcome.changed,
            "message": outcome.message,
        }

    @staticmethod
    def _inventory_outcome_json(
        outcome: AffectedInventoryOutcomeDTO | None,
    ) -> dict[str, object] | None:
        if outcome is None:
            return None
        return {
            "slot_id": outcome.slot_id,
            "item_id": outcome.item_id,
            "quantity_before": outcome.quantity_before,
            "quantity_after": outcome.quantity_after,
            "quantity_delta": outcome.quantity_delta,
            "transaction_type": outcome.transaction_type,
            "transaction_id": outcome.transaction_id,
            "changed": outcome.changed,
            "message": outcome.message,
        }

    @staticmethod
    def _current_operation_outcome(operation: Operation) -> AffectedOperationOutcomeDTO:
        return AffectedOperationOutcomeDTO(
            operation_id=operation.id or 0,
            state=operation.operation_state.value,
            result=operation.result,
            changed=False,
            message="Operation state unchanged by recovery case resolution.",
        )
