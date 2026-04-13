from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.admin_service import AdminUserService
from app.application.dto.admin import AdminRecentOperationDTO
from app.application.exceptions import ValidationError
from app.domain.enums import DispenseRestrictionPolicy, ItemStatus, OperationState, OperationType, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.base import Base
from app.persistence.models import Item, Operation, Role, Slot, User, UserRfidCard
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.users import UserRepository


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'admin_service.sqlite3').resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_import_users_csv_adds_row_context_to_duplicate_rfid_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "operator-1,Operator One,operator,00 0f-e2 76 7c 00 45,once_per_day",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == (
            "CSV row 2: RFID UID '000FE2767C0045' is already assigned to user_code "
            "'user-1' (User One)"
        )


def test_import_users_csv_rejects_invalid_role_code_with_allowed_values(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-2,User Two,manager,,once_per_day",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == (
            "CSV row 2: invalid role_code 'manager'. "
            "Allowed role_code values: admin, operator, user"
        )


def test_import_users_csv_rejects_duplicate_user_code_in_same_payload(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-2,User Two,user,,once_per_day",
                "user-2,User Two Again,user,,unlimited",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == "CSV row 3: duplicate user_code user-2 in import file"


def test_import_users_csv_rejects_header_mismatch_with_expected_and_received_header(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,rfid_uid,role_code,dispense_restriction_policy,unexpected_column",
                "user-2,User Two,,user,once_per_day,extra",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == (
            "CSV header mismatch. Expected: "
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy. "
            "Got: user_code,full_name,rfid_uid,role_code,dispense_restriction_policy,unexpected_column"
        )


@pytest.mark.parametrize(
    ("row_text", "expected_detail"),
    (
        (
            ",User Two,user,,once_per_day",
            "CSV row 2: user_code must not be empty",
        ),
        (
            "user-2,   ,user,,once_per_day",
            "CSV row 2: full_name must not be empty",
        ),
        (
            "user-2,User Two,  ,,once_per_day",
            "CSV row 2: role_code must not be empty",
        ),
        (
            "user-2,User Two,user,,   ",
            "CSV row 2: dispense_restriction_policy must not be empty",
        ),
    ),
)
def test_import_users_csv_rejects_empty_required_fields_with_row_context(
    session_factory: sessionmaker[Session],
    row_text: str,
    expected_detail: str,
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                row_text,
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == expected_detail


def test_export_users_csv_returns_import_compatible_columns_and_current_values(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        exported_csv = service.export_users_csv()

        assert exported_csv == "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-1,User One,user,000FE2767C0045,unlimited",
                "operator-1,Operator One,operator,,once_per_day",
                "",
            )
        )


def test_list_recent_operations_for_admin_returns_newest_first_with_joined_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
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
            drum_position=1,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((item, slot))
        session.flush()

        session.add_all(
            (
                Operation(
                    session_id=None,
                    operation_type=OperationType.REFILL_ITEM,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=4,
                    qty_confirmed=4,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 11, 30, 0),
                    finished_at=datetime(2026, 4, 13, 11, 31, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.FAILED,
                    user_id=1,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=1,
                    qty_confirmed=None,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 10, 0, 0),
                    finished_at=datetime(2026, 4, 13, 10, 1, 0),
                ),
            )
        )
        session.commit()

        rows = OperationRepository(session).list_recent_for_admin(limit=20)

        assert len(rows) == 2
        assert rows[0] == AdminRecentOperationDTO(
            operation_id=rows[0].operation_id,
            started_at=datetime(2026, 4, 13, 11, 30, 0),
            operation_type=OperationType.REFILL_ITEM,
            operation_state=OperationState.COMPLETED,
            user_code="operator-1",
            user_full_name="Operator One",
            item_name="Item One",
            quantity=4,
            slot_code="slot-1",
        )
        assert rows[1] == AdminRecentOperationDTO(
            operation_id=rows[1].operation_id,
            started_at=datetime(2026, 4, 13, 10, 0, 0),
            operation_type=OperationType.DISPENSE,
            operation_state=OperationState.FAILED,
            user_code="user-1",
            user_full_name="User One",
            item_name="Item One",
            quantity=1,
            slot_code="slot-1",
        )


def _seed_import_duplicate_rfid_domain(session: Session) -> None:
    user_role = Role(code=RoleCode.USER, name="User")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add_all((user_role, operator_role))
    session.flush()

    assigned_user = User(
        role_id=user_role.id,
        user_code="user-1",
        full_name="User One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
        is_active=True,
    )
    operator_user = User(
        role_id=operator_role.id,
        user_code="operator-1",
        full_name="Operator One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
        is_active=True,
    )
    session.add_all((assigned_user, operator_user))
    session.flush()

    session.add(
        UserRfidCard(
            user_id=assigned_user.id,
            card_uid="000FE2767C0045",
            is_active=True,
            issued_at=assigned_user.created_at,
            revoked_at=None,
        )
    )
    session.commit()
