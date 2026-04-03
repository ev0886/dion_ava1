from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.rule_evaluation_service import RuleEvaluationService
from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
from app.config import AppSettings
from app.domain.enums import BindingType, ItemStatus, RoleCode, SessionStatus, SessionType, SlotStatus, SlotType, UserStatus
from app.persistence.base import Base
from app.persistence.models import InventoryBalance, Item, OperationSession, Permission, Role, Slot, SlotItemBinding, User
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.operations import OperationSessionRepository
from app.persistence.repositories.users import UserRepository


def test_dispense_rules_allow_happy_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_rule_domain(session)
        service = _build_service(session)

        result = service.evaluate_dispense(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=2)
        )

    assert result.allowed is True
    assert result.reason_codes == ()
    assert result.summary_message == "dispense allowed"
    assert any(rule.code == "dispense_permission_granted" and rule.passed for rule in result.rules)
    assert any(rule.code == "inventory_available" and rule.passed for rule in result.rules)


def test_dispense_rules_reject_insufficient_inventory(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_rule_domain(session, inventory_quantity=1)
        service = _build_service(session)

        result = service.evaluate_dispense(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=2)
        )

    assert result.allowed is False
    assert result.reason_codes == ("insufficient_inventory",)
    assert result.summary_message == "dispense denied: insufficient_inventory"


def test_dispense_rules_reject_blocked_user(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_rule_domain(session, user_status=UserStatus.BLOCKED)
        service = _build_service(session)

        result = service.evaluate_dispense(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1)
        )

    assert result.allowed is False
    assert "user_blocked" in result.reason_codes
    assert any(rule.code == "user_blocked" and rule.passed is False for rule in result.rules)


def test_return_rules_reject_non_returnable_item(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_rule_domain(session, return_allowed=False)
        service = _build_service(session)

        result = service.evaluate_return(
            ReturnRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1)
        )

    assert result.allowed is False
    assert "return_not_allowed" in result.reason_codes
    assert any(rule.code == "return_not_allowed" and rule.passed is False for rule in result.rules)


def test_refill_rules_reject_invalid_session_requirement(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_rule_domain(session, create_refill_session=True, refill_session_status=SessionStatus.COMPLETED)
        service = _build_service(session)

        result = service.evaluate_refill(
            RefillRequest(
                operator_user_id=ids.operator_user_id,
                item_id=ids.item_id,
                slot_id=ids.slot_id,
                quantity=3,
                mode="add",
                session_id=ids.session_id,
            )
        )

    assert result.allowed is False
    assert "refill_session_status_invalid" in result.reason_codes
    assert any(rule.code == "operator_role_allowed" and rule.passed for rule in result.rules)


def test_rule_result_structure_is_explicit_and_deterministic(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_rule_domain(session, create_permission=False)
        service = _build_service(session)

        result = service.evaluate_dispense(
            DispenseRequest(user_id=ids.user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1)
        )

    assert result.allowed is False
    assert result.operation_type.value == "dispense"
    assert result.user_id == ids.user_id
    assert result.item_id == ids.item_id
    assert result.slot_id == ids.slot_id
    assert result.reason_codes == ("dispense_permission_missing",)
    assert result.rules[0].code == "user_active"
    assert result.rules[-1].code in {"inventory_available", "insufficient_inventory"}


class _SeedIds:
    def __init__(
        self,
        *,
        user_id: int,
        operator_user_id: int,
        item_id: int,
        slot_id: int,
        session_id: int | None,
    ) -> None:
        self.user_id = user_id
        self.operator_user_id = operator_user_id
        self.item_id = item_id
        self.slot_id = slot_id
        self.session_id = session_id


def _build_service(session: Session) -> RuleEvaluationService:
    return RuleEvaluationService(
        user_repository=UserRepository(session),
        inventory_repository=InventoryRepository(session),
        session_repository=OperationSessionRepository(session),
    )


def _seed_rule_domain(
    session: Session,
    *,
    inventory_quantity: int = 5,
    user_status: UserStatus = UserStatus.ACTIVE,
    return_allowed: bool = True,
    create_permission: bool = True,
    create_refill_session: bool = False,
    refill_session_status: SessionStatus = SessionStatus.ACTIVE,
) -> _SeedIds:
    user_role = Role(code=RoleCode.USER, name="User")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add_all((user_role, operator_role))
    session.flush()

    user = User(
        role_id=user_role.id,
        user_code="user-1",
        full_name="User One",
        status=user_status,
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
        return_allowed=return_allowed,
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
    session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=inventory_quantity))
    if create_permission:
        session.add(
            Permission(
                user_id=user.id,
                item_id=item.id,
                item_group_id=None,
                can_dispense=True,
                can_return=True,
                valid_from=None,
                valid_to=None,
                comment="seeded permission",
            )
        )

    refill_session = None
    if create_refill_session:
        refill_session = OperationSession(
            session_type=SessionType.SERVICE,
            status=refill_session_status,
            started_by_user_id=operator.id,
            started_at=None,
            finished_at=None,
            comment="seeded service session",
            context_json={},
        )
        session.add(refill_session)

    session.commit()
    return _SeedIds(
        user_id=user.id,
        operator_user_id=operator.id,
        item_id=item.id,
        slot_id=slot.id,
        session_id=refill_session.id if refill_session is not None else None,
    )


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename="rules.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )


def _engine_factory(tmp_path: Path):
    settings = _settings(tmp_path)
    return create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
    )


import pytest


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = _engine_factory(tmp_path)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
