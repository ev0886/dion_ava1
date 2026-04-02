from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.auth_service import AuthService
from app.application.export_service import ExportService
from app.application.service_mode_service import ServiceModeService
from app.config import AppSettings
from app.domain.enums import ExportStatus, ItemStatus, RoleCode, SessionStatus, SlotStatus, SlotType, UserStatus
from app.hardware import HardwareFacade, LockState, MockDrumAdapter, MockHardwareMode, MockLockAdapter, MockRfidAdapter
from app.persistence.base import Base
from app.persistence.models import Export, Item, OperationSession, Role, Slot, User
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationSessionRepository
from app.persistence.repositories.service import ExportRepository
from app.persistence.repositories.users import UserRepository


def test_service_mode_entry_and_exit_result_shape(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service = _service_mode_service(session)

        entered = service.enter_service_mode(user_id=ids.operator_user_id, comment="Maintenance start")
        exited = service.exit_service_mode(
            session_id=entered.session_id or 0,
            user_id=ids.operator_user_id,
            comment="Maintenance done",
        )

        db_session = session.get(OperationSession, entered.session_id)
        assert entered.session_id is not None
        assert entered.status is SessionStatus.ACTIVE
        assert exited.status is SessionStatus.COMPLETED
        assert exited.finished_at is not None
        assert db_session is not None
        assert db_session.status is SessionStatus.COMPLETED


def test_drum_diagnostic_success_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        result = _service_mode_service(session).test_drum_positioning(session_id=None, position=7)

        assert result.ok is True
        assert result.command_name == "test_drum_positioning"
        assert result.payload["position"] == 7


def test_lock_diagnostic_success_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        result = _service_mode_service(session).test_lock_open(session_id=None, board_address=1, lock_number=1)

        assert result.ok is True
        assert result.command_name == "test_lock_open"
        assert result.payload["lock_state"] == LockState.OPEN.value


def test_rfid_read_path(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        service = _service_mode_service(session)
        service.hardware_facade._rfid_reader.queue_card("aa-bb cc")

        result = service.read_rfid(session_id=None)

        assert result.ok is True
        assert result.command_name == "read_rfid"
        assert result.payload["uid"] == "AABBCC"


def test_hardware_failure_returned_as_structured_diagnostic_failure(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        service = _service_mode_service(session, drum_mode=MockHardwareMode.TIMEOUT)

        result = service.test_drum_positioning(session_id=None, position=3)

        assert result.ok is False
        assert result.status == "failure"
        assert result.device_type == "drum_controller"


def test_diagnostic_snapshot_shape(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        snapshot = _service_mode_service(session).get_hardware_snapshot(session_id=11)

        assert snapshot.session_id == 11
        assert len(snapshot.entries) == 3
        assert isinstance(snapshot.overall_ok, bool)
        assert snapshot.entries[0].device_type == "drum_controller"


def test_export_preparation_result_shape(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_users(session)
        service_mode = _service_mode_service(session)
        snapshot = service_mode.get_hardware_snapshot(session_id=15)
        manifest = ExportService.build_diagnostic_dump_manifest(session_id=15, snapshot=snapshot)
        export_service = _export_service(session)

        result = export_service.prepare_export(
            requested_by_user_id=ids.admin_user_id,
            destination_type="filesystem",
            destination_path="var/exports",
            diagnostic_manifest=manifest,
            comment="Prepare diagnostics export",
        )

        export_row = session.get(Export, result.export_id)
        assert result.export_id is not None
        assert result.status is ExportStatus.PENDING
        assert result.manifest is not None
        assert len(result.artifact_plan) == 4
        assert export_row is not None
        assert export_row.destination_path == "var/exports"


class _SeedIds:
    def __init__(self, admin_user_id: int, operator_user_id: int) -> None:
        self.admin_user_id = admin_user_id
        self.operator_user_id = operator_user_id


def _seed_users(session: Session) -> _SeedIds:
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add_all((admin_role, operator_role))
    session.flush()
    admin = User(
        role_id=admin_role.id,
        user_code="admin-1",
        full_name="Admin One",
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
    slot = Slot(
        code="slot-1",
        slot_type=SlotType.UNIVERSAL,
        drum_position=1,
        board_address=1,
        lock_number=1,
        capacity=10,
        status=SlotStatus.ACTIVE,
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
    session.add_all((admin, operator, slot, item))
    session.commit()
    return _SeedIds(admin_user_id=admin.id, operator_user_id=operator.id)


def _service_mode_service(
    session: Session,
    *,
    drum_mode: MockHardwareMode = MockHardwareMode.SUCCESS,
) -> ServiceModeService:
    return ServiceModeService(
        auth_service=AuthService(UserRepository(session)),
        session_repository=OperationSessionRepository(session),
        event_log_repository=EventLogRepository(session),
        audit_log_repository=AuditLogRepository(session),
        hardware_facade=HardwareFacade(
            drum_controller=MockDrumAdapter(initial_position=0, move_mode=drum_mode),
            lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}, unlock_times={1: 5}),
            rfid_reader=MockRfidAdapter(),
        ),
    )


def _export_service(session: Session) -> ExportService:
    return ExportService(
        export_repository=ExportRepository(session),
        event_log_repository=EventLogRepository(session),
        audit_log_repository=AuditLogRepository(session),
    )


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="service_mode.sqlite3",
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
