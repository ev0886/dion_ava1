from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.manual_resolution_service import ManualResolutionPreparationService
from app.application.dto.recovery import InventoryCorrectionRequestDTO, ManualRecoveryActionRequestDTO
from app.application.exceptions import RecoveryError
from app.application.reconciliation_service import RecoveryReconciliationService
from app.application.recovery_service import RecoveryService
from app.application.time import utc_now
from app.domain.enums import (
    ItemStatus,
    InventoryTransactionType,
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.base import Base
from app.persistence.models import (
    InventoryBalance,
    InventoryTransaction,
    Item,
    Operation,
    OperationStateHistory,
    AuditLog,
    EventLog,
    RecoveryCase,
    RecoveryCaseEntity,
    Role,
    Slot,
    User,
)
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'recovery.sqlite3').resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_unfinished_non_terminal_operation_detected_on_startup(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.USER_ACTION_PENDING)
        service = _recovery_service(session)

        result = service.scan_recovery_targets()

        refreshed = session.get(Operation, operation.id)
        history_states = [
            entry.state
            for entry in session.execute(
                select(OperationStateHistory)
                .where(OperationStateHistory.operation_id == operation.id)
                .order_by(OperationStateHistory.id.asc())
            ).scalars()
        ]
        assert refreshed is not None
        assert refreshed.operation_state is OperationState.RECOVERY_REQUIRED
        assert result.unfinished_operation_ids == (operation.id,)
        assert result.candidate_operation_ids == (operation.id,)
        assert history_states[-1] is OperationState.RECOVERY_REQUIRED


def test_completed_operation_ignored_by_recovery_scan(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        _add_operation(session, ids=ids, state=OperationState.COMPLETED)
        service = _recovery_service(session)

        result = service.scan_recovery_targets()

        assert result.candidate_operation_ids == ()
        assert session.execute(select(RecoveryCase)).scalars().all() == []


def test_recovery_case_created_for_uncertain_operation(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.COMPLETION_VERIFICATION)
        service = _recovery_service(session)

        result = service.scan_recovery_targets()

        recovery_case = session.execute(select(RecoveryCase)).scalar_one()
        assert result.candidates[0].operation_id == operation.id
        assert recovery_case.classification is RecoveryClassification.MANUAL_REVIEW_REQUIRED
        assert recovery_case.status is RecoveryStatus.OPEN
        assert recovery_case.context_json["reconciliation_outcome"] == "operation_likely_failed_before_inventory_mutation"


def test_existing_open_recovery_case_reused_instead_of_duplicated(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.RECOVERY_REQUIRED)
        existing_case = RecoveryCase(
            classification=RecoveryClassification.UNCERTAIN_OUTCOME,
            status=RecoveryStatus.OPEN,
            resolved_at=None,
            summary="Existing case",
            context_json={"operation_id": operation.id},
        )
        session.add(existing_case)
        session.flush()
        session.add(
            RecoveryCaseEntity(
                recovery_case_id=existing_case.id,
                entity_type="operation",
                entity_id=str(operation.id),
                role="primary_operation",
                decision_outcome=None,
            )
        )
        session.commit()
        service = _recovery_service(session)

        result = service.scan_recovery_targets()

        cases = session.execute(select(RecoveryCase).order_by(RecoveryCase.id.asc())).scalars().all()
        assert len(cases) == 1
        assert result.candidates[0].recovery_case_id == existing_case.id
        assert result.candidates[0].reused_existing_case is True


def test_reconciliation_reports_missing_inventory_write_when_appropriate(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.INVENTORY_WRITE_PENDING)
        service = RecoveryReconciliationService(InventoryRepository(session))

        result = service.reconcile_operation(operation)

        assert result.outcome == "inventory_write_likely_missing"
        assert result.inventory_transaction_count == 0


def test_reconciliation_reports_no_action_needed_when_consistent(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.INVENTORY_WRITTEN)
        session.add(
            InventoryTransaction(
                slot_id=ids.slot_id,
                item_id=ids.item_id,
                operation_id=operation.id,
                session_id=None,
                transaction_type=InventoryTransactionType.DISPENSE_DEBIT,
                quantity_delta=-1,
                quantity_before=5,
                quantity_after=4,
                comment="Recorded inventory write",
                created_at=utc_now(),
            )
        )
        session.commit()
        service = RecoveryReconciliationService(InventoryRepository(session))

        result = service.reconcile_operation(operation)

        assert result.outcome == "no_action_needed"
        assert result.inventory_transaction_count == 1


def test_manual_resolution_preparation_returns_structured_impacted_entity_context(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.INVENTORY_WRITE_PENDING)
        service = _recovery_service(session)
        scan_result = service.scan_recovery_targets()
        preparation = ManualResolutionPreparationService(RecoveryRepository(session)).prepare_case(
            scan_result.candidates[0].recovery_case_id
        )

        entity_types = {entity.entity_type for entity in preparation.impacted_entities}
        assert preparation.recovery_case_id == scan_result.candidates[0].recovery_case_id
        assert "operation" in entity_types
        assert "item" in entity_types
        assert "slot" in entity_types
        assert "inventory_balance" in entity_types
        assert "verify_inventory_records" in preparation.recommended_next_action_categories
        assert preparation.context["operation_id"] == operation.id


def test_confirm_operation_failed_happy_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.COMPLETION_VERIFICATION)
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id

        result = service.apply_manual_action(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="confirm_operation_failed",
                actor_user_id=ids.user_id,
                comment="Operator confirmed failure",
            )
        )

        refreshed = session.get(Operation, operation.id)
        assert result.recovery_case_id == recovery_case_id
        assert result.case_status is RecoveryStatus.IN_PROGRESS
        assert result.case_resolved is False
        assert result.affected_operation is not None
        assert refreshed is not None
        assert refreshed.operation_state is OperationState.FAILED
        assert refreshed.result == "manually_confirmed_failure"


def test_confirm_operation_succeeded_happy_path_when_evidence_supports_it(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        operation = _add_operation(session, ids=ids, state=OperationState.INVENTORY_WRITTEN)
        session.add(
            InventoryTransaction(
                slot_id=ids.slot_id,
                item_id=ids.item_id,
                operation_id=operation.id,
                session_id=None,
                transaction_type=InventoryTransactionType.DISPENSE_DEBIT,
                quantity_delta=-1,
                quantity_before=5,
                quantity_after=4,
                comment="Recorded inventory write",
                created_at=utc_now(),
            )
        )
        session.commit()
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id

        result = service.apply_manual_action(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="confirm_operation_succeeded",
                actor_user_id=ids.user_id,
                comment="Evidence supports success",
            )
        )

        refreshed = session.get(Operation, operation.id)
        assert result.case_status is RecoveryStatus.IN_PROGRESS
        assert result.affected_operation is not None
        assert refreshed is not None
        assert refreshed.operation_state is OperationState.COMPLETED
        assert refreshed.result == "manually_confirmed_success"
        assert refreshed.error_code is None


def test_manual_inventory_correction_through_recovery_action(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        _add_operation(session, ids=ids, state=OperationState.INVENTORY_WRITE_PENDING)
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id

        result = service.apply_manual_action(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="apply_inventory_correction",
                actor_user_id=ids.user_id,
                comment="Physical count showed one missing item",
                inventory_correction=InventoryCorrectionRequestDTO(
                    slot_id=ids.slot_id,
                    item_id=ids.item_id,
                    quantity_delta=-1,
                ),
            )
        )

        balance = session.execute(
            select(InventoryBalance).where(InventoryBalance.slot_id == ids.slot_id, InventoryBalance.item_id == ids.item_id)
        ).scalar_one()
        transactions = session.execute(select(InventoryTransaction).order_by(InventoryTransaction.id.asc())).scalars().all()
        assert result.case_status is RecoveryStatus.IN_PROGRESS
        assert result.affected_inventory is not None
        assert result.affected_inventory.quantity_after == 4
        assert balance is not None
        assert balance.quantity == 4
        assert transactions[-1].transaction_type is InventoryTransactionType.RECOVERY_ADJUSTMENT


def test_mark_no_action_needed_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        _add_operation(session, ids=ids, state=OperationState.COMPLETION_VERIFICATION)
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id

        result = service.apply_manual_action(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="mark_no_action_needed",
                actor_user_id=ids.user_id,
                comment="Physical inspection found nothing actionable",
            )
        )

        recovery_case = session.get(RecoveryCase, recovery_case_id)
        assert result.case_resolved is True
        assert result.case_status is RecoveryStatus.RESOLVED
        assert result.resolution_code == "no_action_needed"
        assert recovery_case is not None
        assert recovery_case.status is RecoveryStatus.RESOLVED


def test_close_resolve_recovery_case_happy_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        _add_operation(session, ids=ids, state=OperationState.COMPLETION_VERIFICATION)
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id
        service.apply_manual_action(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="confirm_operation_failed",
                actor_user_id=ids.user_id,
                comment="Operator confirmed failure",
            )
        )

        result = service.resolve_case(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="close_recovery_case",
                actor_user_id=ids.user_id,
                comment="Case reconciled and documented",
                resolution_code="manual_failure_confirmed",
            )
        )

        assert result.case_resolved is True
        assert result.case_status is RecoveryStatus.RESOLVED
        assert result.resolution_code == "manual_failure_confirmed"
        assert result.affected_operation is not None
        assert result.affected_operation.changed is False


def test_rejection_when_case_is_already_resolved(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        _add_operation(session, ids=ids, state=OperationState.COMPLETION_VERIFICATION)
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id
        service.resolve_case(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="close_recovery_case",
                actor_user_id=ids.user_id,
                comment="Resolved",
                resolution_code="closed_once",
            )
        )

        with pytest.raises(RecoveryError, match="already resolved"):
            service.apply_manual_action(
                ManualRecoveryActionRequestDTO(
                    recovery_case_id=recovery_case_id,
                    action="confirm_operation_failed",
                    actor_user_id=ids.user_id,
                    comment="Should not be accepted",
                )
            )


def test_rejection_when_action_is_incompatible_with_current_state_or_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        _add_operation(session, ids=ids, state=OperationState.INVENTORY_WRITE_PENDING)
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id

        with pytest.raises(RecoveryError, match="incompatible"):
            service.apply_manual_action(
                ManualRecoveryActionRequestDTO(
                    recovery_case_id=recovery_case_id,
                    action="confirm_operation_succeeded",
                    actor_user_id=ids.user_id,
                    comment="Too little evidence",
                )
            )


def test_audit_log_creation_for_manual_recovery_action(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_domain(session)
        _add_operation(session, ids=ids, state=OperationState.COMPLETION_VERIFICATION)
        service = _recovery_service(session)
        recovery_case_id = service.scan_recovery_targets().candidates[0].recovery_case_id

        service.apply_manual_action(
            ManualRecoveryActionRequestDTO(
                recovery_case_id=recovery_case_id,
                action="confirm_operation_failed",
                actor_user_id=ids.user_id,
                comment="Operator confirmed failure",
            )
        )

        audit_logs = session.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
        assert len(audit_logs) == 1
        assert audit_logs[0].entity_type == "recovery_case"
        assert audit_logs[0].action == "manual_recovery_confirm_operation_failed"
        assert audit_logs[0].actor_user_id == ids.user_id
        assert audit_logs[0].after_json["affected_operation"]["state"] == "failed"
        assert session.execute(select(EventLog)).scalars().all() == []


class _SeedIds:
    def __init__(self, user_id: int, item_id: int, slot_id: int) -> None:
        self.user_id = user_id
        self.item_id = item_id
        self.slot_id = slot_id


def _seed_domain(session: Session) -> _SeedIds:
    role = Role(code=RoleCode.USER, name="User")
    session.add(role)
    session.flush()

    user = User(
        role_id=role.id,
        user_code="user-1",
        full_name="User One",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    item = Item(
        item_group_id=None,
        sku="item-1",
        name="Item One",
        description=None,
        unit="pcs",
        return_allowed=True,
        min_level=0,
        status=ItemStatus.ACTIVE,
    )
    slot = Slot(
        code="slot-1",
        slot_type=SlotType.UNIVERSAL,
        drum_position=2,
        board_address=1,
        lock_number=1,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    session.add_all((user, item, slot))
    session.flush()
    session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=5))
    session.commit()
    return _SeedIds(user_id=user.id, item_id=item.id, slot_id=slot.id)


def _add_operation(session: Session, *, ids: _SeedIds, state: OperationState) -> Operation:
    operation = Operation(
        session_id=None,
        operation_type=OperationType.DISPENSE,
        operation_state=state,
        user_id=ids.user_id,
        item_id=ids.item_id,
        slot_id=ids.slot_id,
        qty_requested=1,
        qty_confirmed=None,
        result=None,
        error_code=None,
        error_message=None,
        hardware_context_json={},
        business_context_json={},
        started_at=utc_now(),
        finished_at=None,
    )
    session.add(operation)
    session.flush()
    session.add(
        OperationStateHistory(
            operation_id=operation.id,
            state=state,
            comment=f"Operation entered {state.value}",
            context_json={},
        )
    )
    session.commit()
    return operation


def _recovery_service(session: Session) -> RecoveryService:
    return RecoveryService(
        RecoveryRepository(session),
        OperationRepository(session),
        InventoryRepository(session),
        EventLogRepository(session),
        AuditLogRepository(session),
    )
