from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.dto.logs import AuditLogQueryFilters, EventLogQueryFilters
from app.application.dto.operations import OperationQueryFilters
from app.application.dto.recovery import RecoveryCaseQueryFilters
from app.application.query_service import LogQueryService, OperationQueryService
from app.application.recovery_service import RecoveryService
from app.application.time import utc_now
from app.domain.enums import (
    InventoryTransactionType,
    OperationState,
    OperationType,
    RecoveryActionStatus,
    RecoveryClassification,
    RecoveryStatus,
)
from app.persistence.base import Base
from app.persistence.models import (
    AuditLog,
    EventLog,
    InventoryTransaction,
    Operation,
    OperationStateHistory,
    RecoveryAction,
    RecoveryCase,
    RecoveryCaseEntity,
)
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'query_reporting.sqlite3').resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_operation_list_happy_path_with_filters(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        seed = _seed_reporting_data(session)
        service = _operation_query_service(session)

        result = service.list_operations(
            OperationQueryFilters(
                operation_type=OperationType.DISPENSE,
                operation_state=OperationState.COMPLETED,
                user_id=seed["user_id"],
                item_id=seed["item_id"],
                slot_id=seed["slot_id"],
                limit=5,
            )
        )

        assert [entry.operation_id for entry in result] == [seed["completed_operation_id"]]


def test_operation_detail_shape(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        seed = _seed_reporting_data(session)
        service = _operation_query_service(session)

        result = service.get_operation(seed["completed_operation_id"])

        assert result.operation.operation_id == seed["completed_operation_id"]
        assert result.recovery_case_id == seed["recovery_case_id"]
        assert [entry.state for entry in result.state_history] == [
            OperationState.CREATED,
            OperationState.COMPLETED,
        ]
        assert [transaction.transaction_id for transaction in result.inventory_transactions] == [
            seed["inventory_transaction_id"]
        ]


def test_operation_history_read_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        seed = _seed_reporting_data(session)
        service = _operation_query_service(session)

        result = service.get_operation_history(seed["pending_operation_id"])

        assert [entry.state for entry in result] == [
            OperationState.CREATED,
            OperationState.USER_ACTION_PENDING,
        ]


def test_recovery_case_list_filter_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        seed = _seed_reporting_data(session)
        service = _recovery_service(session)

        result = service.list_cases(
            RecoveryCaseQueryFilters(
                status=RecoveryStatus.OPEN,
                classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
                limit=10,
            )
        )

        assert [entry.recovery_case_id for entry in result] == [seed["recovery_case_id"]]


def test_recovery_case_detail_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        seed = _seed_reporting_data(session)
        service = _recovery_service(session)

        result = service.get_case_detail(seed["recovery_case_id"])

        assert result.recovery_case_id == seed["recovery_case_id"]
        assert {entity.entity_type for entity in result.impacted_entities} == {"operation", "item", "slot"}
        assert [action.action_type for action in result.recovery_actions] == ["manual_review"]


def test_audit_log_list_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        seed = _seed_reporting_data(session)
        service = _log_query_service(session)

        result = service.list_audit_logs(
            AuditLogQueryFilters(entity_type="operation", actor_user_id=seed["user_id"], limit=10)
        )

        assert [entry.audit_log_id for entry in result] == [seed["audit_log_id"]]


def test_event_log_list_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        seed = _seed_reporting_data(session)
        service = _log_query_service(session)

        result = service.list_event_logs(
            EventLogQueryFilters(event_type="operation.completed", level="info", limit=10)
        )

        assert [entry.event_log_id for entry in result] == [seed["event_log_id"]]
        assert result[0].qty == 1.0


def _seed_reporting_data(session: Session) -> dict[str, int]:
    completed_operation = Operation(
        session_id=1001,
        operation_type=OperationType.DISPENSE,
        operation_state=OperationState.COMPLETED,
        user_id=501,
        item_id=601,
        slot_id=701,
        qty_requested=1,
        qty_confirmed=1,
        result="completed",
        error_code=None,
        error_message=None,
        hardware_context_json={"drum_position": 4},
        business_context_json={"request_source": "operator_cli"},
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    pending_operation = Operation(
        session_id=1002,
        operation_type=OperationType.RETURN,
        operation_state=OperationState.USER_ACTION_PENDING,
        user_id=502,
        item_id=602,
        slot_id=702,
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
    session.add_all((completed_operation, pending_operation))
    session.flush()

    session.add_all(
        (
            OperationStateHistory(
                operation_id=completed_operation.id,
                state=OperationState.CREATED,
                comment="created",
                context_json={},
            ),
            OperationStateHistory(
                operation_id=completed_operation.id,
                state=OperationState.COMPLETED,
                comment="completed",
                context_json={"result": "ok"},
            ),
            OperationStateHistory(
                operation_id=pending_operation.id,
                state=OperationState.CREATED,
                comment="created",
                context_json={},
            ),
            OperationStateHistory(
                operation_id=pending_operation.id,
                state=OperationState.USER_ACTION_PENDING,
                comment="awaiting user",
                context_json={},
            ),
        )
    )

    inventory_transaction = InventoryTransaction(
        slot_id=completed_operation.slot_id or 0,
        item_id=completed_operation.item_id or 0,
        operation_id=completed_operation.id,
        session_id=completed_operation.session_id,
        transaction_type=InventoryTransactionType.DISPENSE_DEBIT,
        quantity_delta=-1,
        quantity_before=5,
        quantity_after=4,
        comment="inventory written",
        created_at=utc_now(),
    )
    session.add(inventory_transaction)
    session.flush()

    recovery_case = RecoveryCase(
        classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
        status=RecoveryStatus.OPEN,
        resolved_at=None,
        summary="Completed operation needs review",
        context_json={"operation_id": completed_operation.id},
    )
    session.add(recovery_case)
    session.flush()

    audit_log = AuditLog(
        entity_type="operation",
        entity_id=str(completed_operation.id),
        action="viewed",
        actor_user_id=completed_operation.user_id,
        reason_code="operator_query",
        comment="Queried operation details",
        before_json={"state": "created"},
        after_json={"state": "completed"},
    )
    event_log = EventLog(
        event_type="operation.completed",
        level="info",
        source="query-test",
        operation_id=completed_operation.id,
        session_id=completed_operation.session_id,
        user_id=completed_operation.user_id,
        slot_id=completed_operation.slot_id,
        item_id=completed_operation.item_id,
        qty=Decimal("1.00"),
        result="completed",
        comment="Operation completed",
        message="Completed for query feed",
        payload_json={"operation_id": completed_operation.id},
    )
    session.add_all(
        (
            RecoveryCaseEntity(
                recovery_case_id=recovery_case.id,
                entity_type="operation",
                entity_id=str(completed_operation.id),
                role="primary_operation",
                decision_outcome=None,
            ),
            RecoveryCaseEntity(
                recovery_case_id=recovery_case.id,
                entity_type="item",
                entity_id=str(completed_operation.item_id),
                role="affected_item",
                decision_outcome=None,
            ),
            RecoveryCaseEntity(
                recovery_case_id=recovery_case.id,
                entity_type="slot",
                entity_id=str(completed_operation.slot_id),
                role="affected_slot",
                decision_outcome=None,
            ),
            RecoveryAction(
                recovery_case_id=recovery_case.id,
                action_type="manual_review",
                status=RecoveryActionStatus.PLANNED,
                applied_at=None,
                comment="Review operator notes",
                context_json={"source": "query_test"},
            ),
            audit_log,
            event_log,
        )
    )
    session.flush()
    session.commit()

    return {
        "user_id": completed_operation.user_id or 0,
        "item_id": completed_operation.item_id or 0,
        "slot_id": completed_operation.slot_id or 0,
        "completed_operation_id": completed_operation.id,
        "pending_operation_id": pending_operation.id,
        "inventory_transaction_id": inventory_transaction.id,
        "recovery_case_id": recovery_case.id,
        "audit_log_id": audit_log.id,
        "event_log_id": event_log.id,
    }


def _operation_query_service(session: Session) -> OperationQueryService:
    return OperationQueryService(
        OperationRepository(session),
        InventoryRepository(session),
        RecoveryRepository(session),
    )


def _recovery_service(session: Session) -> RecoveryService:
    return RecoveryService(
        RecoveryRepository(session),
        OperationRepository(session),
        InventoryRepository(session),
    )


def _log_query_service(session: Session) -> LogQueryService:
    return LogQueryService(AuditLogRepository(session), EventLogRepository(session))
