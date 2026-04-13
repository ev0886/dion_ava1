from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.admin_service import AdminUserService
from app.application.exceptions import ValidationError
from app.domain.enums import DispenseRestrictionPolicy, RoleCode, UserStatus
from app.persistence.base import Base
from app.persistence.models import Role, User, UserRfidCard
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
