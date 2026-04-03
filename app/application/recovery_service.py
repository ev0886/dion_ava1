from __future__ import annotations

from dataclasses import dataclass, field

from app.application.dto.operations import TransitionCheckResult
from app.application.dto.recovery import (
    ManualRecoveryActionRequestDTO,
    RecoveryCandidateDTO,
    RecoveryCaseDTO,
    RecoveryContextDTO,
    RecoveryResolutionResultDTO,
    RecoveryScanResult,
)
from app.application.exceptions import RecoveryError
from app.application.manual_resolution_service import ManualRecoveryActionService, ManualResolutionPreparationService
from app.application.operation_recorder import OperationRecorder
from app.application.reconciliation_service import RecoveryReconciliationService
from app.application.state_machine import assert_transition_allowed, can_transition
from app.domain.enums import OperationState, OperationType, RecoveryClassification, RecoveryStatus
from app.persistence.models import Operation, RecoveryCase, RecoveryCaseEntity
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository


@dataclass(slots=True)
class RecoveryService:
    recovery_repository: RecoveryRepository
    operation_repository: OperationRepository
    inventory_repository: InventoryRepository
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository
    _recorder: OperationRecorder = field(init=False, repr=False)
    _reconciliation_service: RecoveryReconciliationService = field(init=False, repr=False)
    _manual_resolution_service: ManualResolutionPreparationService = field(init=False, repr=False)
    _manual_recovery_action_service: ManualRecoveryActionService = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._recorder = OperationRecorder(self.operation_repository)
        self._reconciliation_service = RecoveryReconciliationService(self.inventory_repository)
        self._manual_resolution_service = ManualResolutionPreparationService(self.recovery_repository)
        self._manual_recovery_action_service = ManualRecoveryActionService(
            recovery_repository=self.recovery_repository,
            operation_repository=self.operation_repository,
            inventory_repository=self.inventory_repository,
            event_log_repository=self.event_log_repository,
            audit_log_repository=self.audit_log_repository,
        )

    def get_case(self, recovery_case_id: int) -> RecoveryCaseDTO:
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            raise RecoveryError(f"Recovery case not found: {recovery_case_id}")
        return self._to_dto(recovery_case)

    def list_open_cases(self) -> tuple[RecoveryCaseDTO, ...]:
        return tuple(self._to_dto(case) for case in self.recovery_repository.list_open_cases())

    def scan_recovery_targets(self) -> RecoveryScanResult:
        unfinished_operation_ids = tuple(operation.id for operation in self.operation_repository.list_unfinished())
        candidates: list[RecoveryCandidateDTO] = []

        for operation in self.operation_repository.list_recovery_scan_candidates():
            if operation.id is None:
                continue
            if operation.operation_state in self._terminal_states():
                continue

            detected_state = operation.operation_state
            reconciliation = self._reconciliation_service.reconcile_operation(operation)
            classification = self._classify_recovery_case(reconciliation.outcome)
            recovery_case, reused_existing_case = self._ensure_recovery_case(
                operation,
                classification=classification,
                reconciliation_outcome=reconciliation.outcome,
                reconciliation_reason=reconciliation.reason,
                inventory_transaction_ids=reconciliation.inventory_transaction_ids,
            )
            self._mark_operation_for_recovery(operation, recovery_case.id, reconciliation.outcome)
            candidates.append(
                RecoveryCandidateDTO(
                    operation_id=operation.id,
                    detected_state=detected_state.value,
                    classification=classification,
                    reconciliation_outcome=reconciliation.outcome,
                    recovery_case_id=recovery_case.id,
                    reused_existing_case=reused_existing_case,
                )
            )

        self.operation_repository.session.commit()
        open_cases = self.list_open_cases()
        return RecoveryScanResult(
            open_case_count=len(open_cases),
            open_cases=open_cases,
            unfinished_operation_ids=unfinished_operation_ids,
            candidate_operation_ids=tuple(candidate.operation_id for candidate in candidates),
            candidates=tuple(candidates),
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

    def prepare_manual_resolution(self, recovery_case_id: int):
        return self._manual_resolution_service.prepare_case(recovery_case_id)

    def apply_manual_action(self, request: ManualRecoveryActionRequestDTO) -> RecoveryResolutionResultDTO:
        return self._manual_recovery_action_service.apply_action(request)

    def resolve_case(self, request: ManualRecoveryActionRequestDTO) -> RecoveryResolutionResultDTO:
        return self._manual_recovery_action_service.resolve_case(request)

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
        )

    @staticmethod
    def _classify_recovery_case(reconciliation_outcome: str) -> RecoveryClassification:
        if reconciliation_outcome == "inventory_write_likely_missing":
            return RecoveryClassification.PENDING_INVENTORY_WRITE
        if reconciliation_outcome == "no_action_needed":
            return RecoveryClassification.UNCERTAIN_OUTCOME
        return RecoveryClassification.MANUAL_REVIEW_REQUIRED

    def _ensure_recovery_case(
        self,
        operation: Operation,
        *,
        classification: RecoveryClassification,
        reconciliation_outcome: str,
        reconciliation_reason: str,
        inventory_transaction_ids: tuple[int, ...],
    ) -> tuple[RecoveryCase, bool]:
        existing_case = self.recovery_repository.find_open_case_by_operation_id(operation.id or 0)
        summary = self._build_summary(operation, reconciliation_outcome)
        context = {
            "operation_id": operation.id,
            "operation_type": operation.operation_type.value,
            "detected_state": operation.operation_state.value,
            "reconciliation_outcome": reconciliation_outcome,
            "reconciliation_reason": reconciliation_reason,
            "inventory_transaction_ids": list(inventory_transaction_ids),
        }
        if existing_case is not None:
            existing_case.classification = classification
            existing_case.status = RecoveryStatus.OPEN
            existing_case.summary = summary
            existing_case.context_json = {**dict(existing_case.context_json or {}), **context}
            self._ensure_case_entities(existing_case.id, operation, inventory_transaction_ids)
            self.recovery_repository.session.flush()
            return (existing_case, True)

        recovery_case = RecoveryCase(
            classification=classification,
            status=RecoveryStatus.OPEN,
            resolved_at=None,
            summary=summary,
            context_json=context,
        )
        self.recovery_repository.add_case(recovery_case)
        self.recovery_repository.session.flush()
        self._ensure_case_entities(recovery_case.id, operation, inventory_transaction_ids)
        return (recovery_case, False)

    def _ensure_case_entities(
        self,
        recovery_case_id: int,
        operation: Operation,
        inventory_transaction_ids: tuple[int, ...],
    ) -> None:
        entities: list[tuple[str, str, str]] = [("operation", str(operation.id), "primary_operation")]
        if operation.session_id is not None:
            entities.append(("operation_session", str(operation.session_id), "parent_session"))
        if operation.item_id is not None:
            entities.append(("item", str(operation.item_id), "affected_item"))
        if operation.slot_id is not None:
            entities.append(("slot", str(operation.slot_id), "affected_slot"))
        if operation.slot_id is not None and operation.item_id is not None:
            entities.append(
                (
                    "inventory_balance",
                    f"slot:{operation.slot_id}:item:{operation.item_id}",
                    "inventory_snapshot_target",
                )
            )
        for transaction_id in inventory_transaction_ids:
            entities.append(("inventory_transaction", str(transaction_id), "inventory_evidence"))

        for entity_type, entity_id, role in entities:
            if self.recovery_repository.get_case_entity(
                recovery_case_id,
                entity_type=entity_type,
                entity_id=entity_id,
                role=role,
            ):
                continue
            self.recovery_repository.add_case_entity(
                RecoveryCaseEntity(
                    recovery_case_id=recovery_case_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    role=role,
                    decision_outcome=None,
                )
            )
        self.recovery_repository.session.flush()

    def _mark_operation_for_recovery(
        self,
        operation: Operation,
        recovery_case_id: int,
        reconciliation_outcome: str,
    ) -> None:
        if operation.operation_state is OperationState.RECOVERY_REQUIRED:
            return
        self._recorder.transition(
            operation,
            OperationState.RECOVERY_REQUIRED,
            comment="Startup recovery scan marked operation for explicit recovery handling",
            history_context={
                "recovery_case_id": recovery_case_id,
                "reconciliation_outcome": reconciliation_outcome,
                "startup_scan": True,
            },
        )

    @staticmethod
    def _build_summary(operation: Operation, reconciliation_outcome: str) -> str:
        return (
            f"Operation {operation.id} ({operation.operation_type.value}) stopped in "
            f"{operation.operation_state.value}; reconciliation outcome: {reconciliation_outcome}."
        )

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
