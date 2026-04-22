from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.application.dispense_service import DispenseOperationService
from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
from app.application.refill_service import RefillOperationService
from app.application.return_service import ReturnOperationService
from app.config import AppSettings
from app.domain.enums import (
    BindingType,
    DispenseRestrictionPolicy,
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
from app.application.exceptions import ValidationError
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


class _AllowAllOpenDoorGuard:
    def assert_all_closed(self, *, action_description: str) -> None:
        return None


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
        service = DispenseOperationService(OperationRepository(session), InventoryRepository(session), _AllowAllOpenDoorGuard())

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


def test_dispense_zero_post_move_unlock_delay_does_not_sleep(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=5)
        sleep_calls: list[float] = []
        service = DispenseOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            _AllowAllOpenDoorGuard(),
            post_move_unlock_delay_ms=0,
            _sleep=sleep_calls.append,
        )

        result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _hardware_facade(),
        )

        assert result.operation_state is OperationState.COMPLETED
        assert sleep_calls == []


def test_dispense_configured_post_move_unlock_delay_runs_between_move_and_unlock(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=5)
        call_order: list[str] = []
        sleep_calls: list[float] = []
        service = DispenseOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            _AllowAllOpenDoorGuard(),
            post_move_unlock_delay_ms=1500,
            _sleep=lambda seconds: (sleep_calls.append(seconds), call_order.append("sleep")),
        )

        result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _RecordingHardwareFacade(call_order),
        )

        assert result.operation_state is OperationState.COMPLETED
        assert sleep_calls == [1.5]
        assert call_order == ["move", "sleep", "unlock"]


def test_successful_return_flow_with_mock_hardware(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=1)
        service = ReturnOperationService(OperationRepository(session), InventoryRepository(session), _AllowAllOpenDoorGuard())

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
            _AllowAllOpenDoorGuard(),
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
        service = DispenseOperationService(OperationRepository(session), InventoryRepository(session), _AllowAllOpenDoorGuard())
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


def test_refill_hardware_failure_marks_session_failed_without_inventory_mutation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=5)
        service = RefillOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            OperationSessionRepository(session),
            _AllowAllOpenDoorGuard(),
        )

        result = service.execute(
            RefillRequest(
                operator_user_id=ids.operator_user_id,
                item_id=ids.item_id,
                slot_id=ids.slot_id,
                quantity=3,
                mode="add",
            ),
            _hardware_facade(drum_mode=MockHardwareMode.TIMEOUT),
        )

        balance = session.execute(select(InventoryBalance)).scalar_one()
        refill_session = session.get(OperationSession, result.session_id)
        transactions = session.execute(select(InventoryTransaction)).scalars().all()
        assert result.operation_state is OperationState.FAILED
        assert balance.quantity == 5
        assert refill_session is not None
        assert refill_session.status is SessionStatus.FAILED
        assert refill_session.finished_at is not None
        assert transactions == []


def test_operation_history_entries_are_written(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=5)
        service = DispenseOperationService(OperationRepository(session), InventoryRepository(session), _AllowAllOpenDoorGuard())

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


def test_once_per_day_policy_blocks_second_successful_dispense_same_day(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(
            session,
            starting_quantity=5,
            user_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
        )
        service = DispenseOperationService(OperationRepository(session), InventoryRepository(session), _AllowAllOpenDoorGuard())
        first_result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _hardware_facade(),
        )

        with pytest.raises(ValidationError, match="one successful dispense per day"):
            service.execute(
                DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
                _hardware_facade(),
            )

        assert first_result.operation_state is OperationState.COMPLETED


def test_once_per_day_policy_ignores_failed_dispense_attempts(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(
            session,
            starting_quantity=5,
            user_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
        )
        service = DispenseOperationService(OperationRepository(session), InventoryRepository(session), _AllowAllOpenDoorGuard())

        failed_result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _hardware_facade(drum_mode=MockHardwareMode.TIMEOUT),
        )
        successful_result = service.execute(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _hardware_facade(),
        )

        assert failed_result.operation_state is OperationState.FAILED
        assert successful_result.operation_state is OperationState.COMPLETED


def test_user_policy_orm_loads_legacy_uppercase_and_lowercase_storage(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_catalog(
            session,
            starting_quantity=5,
            user_policy=DispenseRestrictionPolicy.UNLIMITED,
        )
        session.execute(
            text(
                """
                UPDATE users
                SET dispense_restriction_policy = CASE id
                    WHEN :user_id THEN 'UNLIMITED'
                    WHEN :operator_user_id THEN 'once_per_day'
                END
                WHERE id IN (:user_id, :operator_user_id)
                """
            ),
            {"user_id": ids.user_id, "operator_user_id": ids.operator_user_id},
        )
        session.commit()
        session.expire_all()

        user = session.get(User, ids.user_id)
        operator = session.get(User, ids.operator_user_id)

        assert user is not None
        assert operator is not None
        assert user.dispense_restriction_policy is DispenseRestrictionPolicy.UNLIMITED
        assert operator.dispense_restriction_policy is DispenseRestrictionPolicy.ONCE_PER_DAY


def test_inventory_transaction_rows_are_written_for_successful_inventory_flows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_catalog(session, starting_quantity=10)
        inventory_repository = InventoryRepository(session)

        dispense_service = DispenseOperationService(OperationRepository(session), inventory_repository, _AllowAllOpenDoorGuard())
        return_service = ReturnOperationService(OperationRepository(session), inventory_repository, _AllowAllOpenDoorGuard())
        refill_service = RefillOperationService(
            OperationRepository(session),
            inventory_repository,
            OperationSessionRepository(session),
            _AllowAllOpenDoorGuard(),
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


def _seed_catalog(
    session: Session,
    *,
    starting_quantity: int,
    user_policy: DispenseRestrictionPolicy = DispenseRestrictionPolicy.UNLIMITED,
) -> _SeedIds:
    user_role = Role(code=RoleCode.USER, name="User")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add_all((user_role, operator_role))
    session.flush()

    user = User(
        role_id=user_role.id,
        user_code="user-1",
        full_name="User One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=user_policy,
        is_active=True,
    )
    operator = User(
        role_id=operator_role.id,
        user_code="operator-1",
        full_name="Operator One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
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


class _RecordingHardwareFacade:
    def __init__(self, call_order: list[str]) -> None:
        self._call_order = call_order
        self._delegate = _hardware_facade()

    def move_drum_to_position(self, position: int):
        self._call_order.append("move")
        return self._delegate.move_drum_to_position(position)

    def unlock_lock(self, board_address: int, lock_number: int):
        self._call_order.append("unlock")
        return self._delegate.unlock_lock(board_address, lock_number)
