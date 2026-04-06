from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.dispense_service import DispenseOperationService
from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
from app.application.refill_service import RefillOperationService
from app.application.return_service import ReturnOperationService
from app.config import AppSettings
from app.domain.enums import (
    BindingType,
    ItemStatus,
    InventoryTransactionType,
    OperationState,
    RoleCode,
    SessionStatus,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.hardware import HardwareFacade, LockState, MockDrumAdapter, MockHardwareMode, MockLockAdapter, MockRfidAdapter
from app.persistence.base import Base
from app.persistence.models import (
    InventoryBalance,
    InventoryTransaction,
    Item,
    Operation,
    OperationSession,
    OperationStateHistory,
    Role,
    Slot,
    SlotItemBinding,
    User,
)
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.operations import OperationRepository, OperationSessionRepository


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="orchestration.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )
    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_successful_dispense_flow_with_mock_hardware(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=5)
        service = DispenseOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            OperationSessionRepository(session),
        )

        result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=2),
            _hardware_facade(),
        )

        balance = session.execute(select(InventoryBalance)).scalar_one()
        operation = session.get(Operation, result.operation_id)
        assert result.operation_state is OperationState.COMPLETED
        assert balance.quantity == 3
        assert operation is not None
        assert operation.operation_state is OperationState.COMPLETED
        assert operation.qty_confirmed == 2


def test_successful_return_flow_with_mock_hardware(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=1)
        service = ReturnOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            OperationSessionRepository(session),
        )

        result = service.execute(
            ReturnRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=None, quantity=2),
            _hardware_facade(),
        )

        balance = session.execute(select(InventoryBalance)).scalar_one()
        assert result.operation_state is OperationState.COMPLETED
        assert result.slot_id == ids.slot_id
        assert balance.quantity == 3


def test_successful_refill_flow_with_mock_hardware(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=4)
        service = RefillOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            OperationSessionRepository(session),
        )

        result = service.execute(
            RefillRequest(
                operator_user_id=ids.operator_user_id,
                item_id=ids.item_id,
                slot_id=ids.slot_id,
                quantity=3,
                mode="add",
            ),
            _hardware_facade(),
        )

        balance = session.execute(select(InventoryBalance)).scalar_one()
        refill_session = session.get(OperationSession, result.session_id)
        assert result.operation_state is OperationState.SESSION_COMPLETED
        assert balance.quantity == 7
        assert refill_session is not None
        assert refill_session.status is SessionStatus.COMPLETED


def test_dispense_hardware_failure_does_not_mutate_inventory_incorrectly(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=5)
        service = DispenseOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            OperationSessionRepository(session),
        )
        failing_facade = _hardware_facade(drum_mode=MockHardwareMode.TIMEOUT)

        result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=2),
            failing_facade,
        )

        balance = session.execute(select(InventoryBalance)).scalar_one()
        transactions = session.execute(select(InventoryTransaction)).scalars().all()
        assert result.operation_state is OperationState.FAILED
        assert balance.quantity == 5
        assert transactions == []


def test_operation_history_entries_are_written(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=5)
        service = DispenseOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            OperationSessionRepository(session),
        )

        result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _hardware_facade(),
        )

        history_states = [
            entry.state
            for entry in session.execute(
                select(OperationStateHistory)
                .where(OperationStateHistory.operation_id == result.operation_id)
                .order_by(OperationStateHistory.id.asc())
            ).scalars()
        ]
        assert history_states[0] is OperationState.CREATED
        assert OperationState.POSITIONING_REQUESTED in history_states
        assert OperationState.UNLOCK_COMPLETED in history_states
        assert history_states[-1] is OperationState.COMPLETED


def test_inventory_transaction_rows_are_written_for_successful_inventory_flows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=10)
        inventory_repository = InventoryRepository(session)

        dispense_service = DispenseOperationService(
            OperationRepository(session),
            inventory_repository,
            OperationSessionRepository(session),
        )
        return_service = ReturnOperationService(
            OperationRepository(session),
            inventory_repository,
            OperationSessionRepository(session),
        )
        refill_service = RefillOperationService(
            OperationRepository(session),
            inventory_repository,
            OperationSessionRepository(session),
        )

        dispense_service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=2),
            _hardware_facade(),
        )
        return_service.execute(
            ReturnRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _hardware_facade(),
        )
        refill_service.execute(
            RefillRequest(
                operator_user_id=ids.operator_user_id,
                item_id=ids.item_id,
                slot_id=ids.slot_id,
                quantity=12,
                mode="set",
            ),
            _hardware_facade(),
        )

        transaction_types = [
            transaction.transaction_type
            for transaction in session.execute(
                select(InventoryTransaction).order_by(InventoryTransaction.id.asc())
            ).scalars()
        ]
        assert transaction_types == [
            InventoryTransactionType.DISPENSE_DEBIT,
            InventoryTransactionType.RETURN_CREDIT,
            InventoryTransactionType.REFILL_SET,
        ]


class _SeedIds:
    def __init__(self, user_id: int, operator_user_id: int, item_id: int, slot_id: int) -> None:
        self.user_id = user_id
        self.operator_user_id = operator_user_id
        self.item_id = item_id
        self.slot_id = slot_id


def _seed_catalog(session: Session, *, starting_quantity: int) -> _SeedIds:
    user_role = Role(code=RoleCode.USER, name="User")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add_all((user_role, operator_role))
    session.flush()

    user = User(
        role_id=user_role.id,
        user_code="user-1",
        full_name="User One",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    operator = User(
        role_id=operator_role.id,
        user_code="operator-1",
        full_name="Operator One",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    session.add_all((user, operator))
    session.flush()

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
        drum_position=4,
        board_address=1,
        lock_number=1,
        capacity=20,
        status=SlotStatus.ACTIVE,
    )
    session.add_all((item, slot))
    session.flush()

    session.add(
        SlotItemBinding(
            slot_id=slot.id,
            item_id=item.id,
            binding_type=BindingType.RETURN,
            is_active=True,
            valid_from=None,
            valid_to=None,
        )
    )
    session.add(
        InventoryBalance(
            slot_id=slot.id,
            item_id=item.id,
            quantity=starting_quantity,
        )
    )
    session.commit()
    return _SeedIds(user_id=user.id, operator_user_id=operator.id, item_id=item.id, slot_id=slot.id)


def _hardware_facade(drum_mode: MockHardwareMode = MockHardwareMode.SUCCESS) -> HardwareFacade:
    return HardwareFacade(
        drum_controller=MockDrumAdapter(initial_position=0, move_mode=drum_mode),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=MockRfidAdapter(),
    )
