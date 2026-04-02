from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.auth_service import AuthService
from app.application.exceptions import AuthorizationError, InvalidStateTransitionError
from app.application.import_export_service import ImportExportPreparationService
from app.application.rfid_binding_service import RfidBindingService
from app.application.dto.import_export import ExportPreparationRequest, ImportPreparationRequest
from app.config import AppSettings
from app.domain.enums import RoleCode, UserStatus
from app.persistence.base import Base
from app.persistence.models import AuditLog, EventLog, Role, User, UserRfidCard
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.users import UserRepository


def test_rfid_bind_happy_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service = _rfid_service(session)

        result = service.bind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, card_uid="aa-bb cc")

        card = session.query(UserRfidCard).filter_by(user_id=ids.user_user_id, is_active=True).one()
        assert result.action == "bind"
        assert result.card_uid == "AABBCC"
        assert card.card_uid == "AABBCC"
        assert card.revoked_at is None


def test_rfid_duplicate_rejection(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service = _rfid_service(session)
        service.bind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, card_uid="A1")

        with pytest.raises(InvalidStateTransitionError, match="already assigned"):
            service.bind_card(actor_user_id=ids.admin_user_id, user_id=ids.second_user_id, card_uid="A1")


def test_rfid_rebind_replace_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service = _rfid_service(session)
        service.bind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, card_uid="AA11")

        result = service.rebind_card(
            actor_user_id=ids.admin_user_id,
            user_id=ids.user_user_id,
            card_uid="BB22",
            comment="replace",
        )

        active_cards = session.query(UserRfidCard).filter_by(user_id=ids.user_user_id, is_active=True).all()
        revoked_cards = session.query(UserRfidCard).filter_by(user_id=ids.user_user_id, is_active=False).all()
        assert result.action == "rebind"
        assert result.previous_card_uid == "AA11"
        assert result.card_uid == "BB22"
        assert len(active_cards) == 1
        assert active_cards[0].card_uid == "BB22"
        assert len(revoked_cards) == 1
        assert revoked_cards[0].revoked_at is not None


def test_rfid_unbind_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service = _rfid_service(session)
        service.bind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, card_uid="AA11")

        result = service.unbind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, comment="remove")

        active_card = session.query(UserRfidCard).filter_by(user_id=ids.user_user_id, is_active=True).one_or_none()
        revoked_card = session.query(UserRfidCard).filter_by(user_id=ids.user_user_id, is_active=False).one()
        assert result.action == "unbind"
        assert result.card_uid is None
        assert result.previous_card_uid == "AA11"
        assert active_card is None
        assert revoked_card.revoked_at is not None


def test_rfid_actions_create_audit_entries(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service = _rfid_service(session)

        service.bind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, card_uid="AA11", comment="bind")
        service.rebind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, card_uid="BB22", comment="swap")
        service.unbind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, comment="remove")

        audit_actions = [row.action for row in session.query(AuditLog).order_by(AuditLog.id.asc()).all()]
        event_types = [row.event_type for row in session.query(EventLog).order_by(EventLog.id.asc()).all()]
        assert audit_actions == ["rfid_bind", "rfid_rebind", "rfid_unbind"]
        assert event_types == ["rfid_card_bound", "rfid_card_rebound", "rfid_card_unbound"]


def test_rfid_bind_rejects_inactive_target_user(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session, target_status=UserStatus.BLOCKED)
        service = _rfid_service(session)

        with pytest.raises(AuthorizationError, match="blocked"):
            service.bind_card(actor_user_id=ids.admin_user_id, user_id=ids.user_user_id, card_uid="AA11")


def test_user_item_import_export_preparation_result_shapes(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service = ImportExportPreparationService(auth_service=AuthService(UserRepository(session)))

        user_import = service.prepare_import(
            ImportPreparationRequest(
                requested_by_user_id=ids.admin_user_id,
                entity_type="users",
                source_type="filesystem",
                source_path="var/imports/users.csv",
                format_type="csv",
            )
        )
        item_export = service.prepare_export(
            ExportPreparationRequest(
                requested_by_user_id=ids.admin_user_id,
                entity_type="items",
                destination_type="filesystem",
                destination_path="var/exports/items.xlsx",
                format_type="xlsx",
                include_inactive=True,
            )
        )

        assert user_import.entity_type == "users"
        assert user_import.required_fields == ("user_code", "full_name", "role_code", "status", "is_active")
        assert user_import.row_schema[-1].field_name == "rfid_uid"
        assert user_import.artifact_plan[0].file_name == "users_import.csv"
        assert item_export.entity_type == "items"
        assert item_export.row_schema[-1].field_type == "integer"
        assert item_export.artifact_plan[0].file_name == "items_export.xlsx"
        assert item_export.include_inactive is True


class _SeedIds:
    def __init__(self, *, admin_user_id: int, user_user_id: int, second_user_id: int) -> None:
        self.admin_user_id = admin_user_id
        self.user_user_id = user_user_id
        self.second_user_id = second_user_id


def _seed_users(session: Session, *, target_status: UserStatus = UserStatus.ACTIVE) -> _SeedIds:
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    user_role = Role(code=RoleCode.USER, name="User")
    session.add_all((admin_role, user_role))
    session.flush()
    admin = User(
        role_id=admin_role.id,
        user_code="admin-1",
        full_name="Admin One",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    user = User(
        role_id=user_role.id,
        user_code="user-1",
        full_name="User One",
        status=target_status,
        is_active=True,
    )
    second_user = User(
        role_id=user_role.id,
        user_code="user-2",
        full_name="User Two",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    session.add_all((admin, user, second_user))
    session.commit()
    return _SeedIds(admin_user_id=admin.id, user_user_id=user.id, second_user_id=second_user.id)


def _rfid_service(session: Session) -> RfidBindingService:
    user_repository = UserRepository(session)
    return RfidBindingService(
        auth_service=AuthService(user_repository),
        user_repository=user_repository,
        event_log_repository=EventLogRepository(session),
        audit_log_repository=AuditLogRepository(session),
    )


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="rfid.sqlite3",
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
