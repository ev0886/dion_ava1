from __future__ import annotations

from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api import create_app
from app.application.authorization_service import AuthorizationService
from app.application.dispense_service import DispenseOperationService
from app.application.dto.auth import AuthorizationRequest
from app.application.dto.operations import DispenseRequest
from app.application.exceptions import AuthorizationError
from app.cli import main
from app.config import AppSettings
from app.domain.enums import (
    AuthorizationAction,
    BindingType,
    ItemStatus,
    OperationState,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.hardware import HardwareFacade, LockState, MockDrumAdapter, MockLockAdapter, MockRfidAdapter
from app.persistence.base import Base
from app.persistence.models import AuditLog, Export, InventoryBalance, Item, Operation, Role, Slot, SlotItemBinding, User
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository, OperationSessionRepository
from app.persistence.repositories.service import ExportRepository
from app.persistence.repositories.users import UserRepository
from app.application.export_service import ExportService
from app.application.service_mode_service import ServiceModeService


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'authz.sqlite3').resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_admin_allowed_on_representative_admin_mutation(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_authorization_domain(session)
        result = _export_service(session).prepare_export(
            requested_by_user_id=ids.admin_user_id,
            destination_type="filesystem",
            destination_path="var/exports",
            diagnostic_manifest=None,
        )

        export_row = session.get(Export, result.export_id)
        assert export_row is not None
        assert export_row.requested_by_user_id == ids.admin_user_id


def test_operator_denied_on_representative_admin_mutation(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_authorization_domain(session)

        with pytest.raises(AuthorizationError) as error_info:
            _export_service(session).prepare_export(
                requested_by_user_id=ids.operator_user_id,
                destination_type="filesystem",
                destination_path="var/exports",
                diagnostic_manifest=None,
            )

        denial = session.execute(select(AuditLog).order_by(AuditLog.id.desc())).scalar_one()
        assert error_info.value.reason_code is not None
        assert error_info.value.reason_code.value == "role_not_allowed"
        assert denial.reason_code == "role_not_allowed"


def test_operator_allowed_on_representative_operational_action(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_authorization_domain(session)

        result = _service_mode_service(session).enter_service_mode(user_id=ids.operator_user_id, comment="ops")

        assert result.started_by_user_id == ids.operator_user_id
        assert result.status.value == "active"


def test_blocked_actor_denied(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_authorization_domain(session)

        with pytest.raises(AuthorizationError) as error_info:
            _service_mode_service(session).enter_service_mode(user_id=ids.blocked_operator_user_id, comment="blocked")

        assert error_info.value.reason_code is not None
        assert error_info.value.reason_code.value == "actor_blocked"


def test_inactive_actor_denied(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_authorization_domain(session)

        with pytest.raises(AuthorizationError) as error_info:
            _service_mode_service(session).enter_service_mode(user_id=ids.inactive_operator_user_id, comment="inactive")

        assert error_info.value.reason_code is not None
        assert error_info.value.reason_code.value == "actor_inactive"


def test_missing_actor_denied(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _seed_authorization_domain(session)

        with pytest.raises(AuthorizationError) as error_info:
            _authorization_service(session).require(
                AuthorizationRequest(
                    action=AuthorizationAction.RECOVERY_SCAN,
                    actor_user_id=None,
                )
            )

        assert error_info.value.reason_code is not None
        assert error_info.value.reason_code.value == "missing_actor"


def test_api_denial_mapping_for_protected_route(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_authz.sqlite3"))
    _seed_api_authorization_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/exports/create",
            json={"requested_by_user_id": 2, "destination_type": "filesystem", "destination_path": "var/exports"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "authorization_error"
    assert response.json()["reason_code"] == "role_not_allowed"
    assert response.json()["action"] == "export_execution"


def test_cli_denial_behavior_for_protected_command(tmp_path: Path) -> None:
    _seed_cli_authorization_domain(tmp_path, "cli_authz.sqlite3")

    exit_code, _stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_authz.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "export-plan",
            "--requested-by-user-id",
            "2",
        ]
    )

    assert exit_code == 1
    assert "ERROR: Actor role is not allowed for action: export_execution" in stderr


def test_authorized_operational_path_keeps_successful_hardware_behavior(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids = _seed_authorization_domain(session)
        service = DispenseOperationService(
            OperationRepository(session),
            InventoryRepository(session),
            _authorization_service(session),
        )

        result = service.execute(
            DispenseRequest(user_id=ids.operator_user_id, item_id=ids.item_id, slot_id=ids.slot_id, quantity=1),
            _hardware_facade(),
        )

        balance = session.execute(select(InventoryBalance)).scalar_one()
        operation = session.get(Operation, result.operation_id)
        assert result.operation_state is OperationState.COMPLETED
        assert balance.quantity == 4
        assert operation is not None
        assert operation.operation_state is OperationState.COMPLETED


class _SeedIds:
    def __init__(
        self,
        *,
        admin_user_id: int,
        operator_user_id: int,
        blocked_operator_user_id: int,
        inactive_operator_user_id: int,
        item_id: int,
        slot_id: int,
    ) -> None:
        self.admin_user_id = admin_user_id
        self.operator_user_id = operator_user_id
        self.blocked_operator_user_id = blocked_operator_user_id
        self.inactive_operator_user_id = inactive_operator_user_id
        self.item_id = item_id
        self.slot_id = slot_id


def _seed_authorization_domain(session: Session) -> _SeedIds:
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
    blocked_operator = User(
        role_id=operator_role.id,
        user_code="operator-2",
        full_name="Operator Blocked",
        status=UserStatus.BLOCKED,
        is_active=True,
    )
    inactive_operator = User(
        role_id=operator_role.id,
        user_code="operator-3",
        full_name="Operator Inactive",
        status=UserStatus.INACTIVE,
        is_active=False,
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
        drum_position=3,
        board_address=1,
        lock_number=1,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    session.add_all((admin, operator, blocked_operator, inactive_operator, item, slot))
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
    session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=5))
    session.commit()
    return _SeedIds(
        admin_user_id=admin.id,
        operator_user_id=operator.id,
        blocked_operator_user_id=blocked_operator.id,
        inactive_operator_user_id=inactive_operator.id,
        item_id=item.id,
        slot_id=slot.id,
    )


def _authorization_service(session: Session) -> AuthorizationService:
    return AuthorizationService(UserRepository(session), AuditLogRepository(session))


def _export_service(session: Session) -> ExportService:
    return ExportService(
        export_repository=ExportRepository(session),
        event_log_repository=EventLogRepository(session),
        audit_log_repository=AuditLogRepository(session),
        authorization_service=_authorization_service(session),
    )


def _service_mode_service(session: Session) -> ServiceModeService:
    return ServiceModeService(
        authorization_service=_authorization_service(session),
        session_repository=OperationSessionRepository(session),
        event_log_repository=EventLogRepository(session),
        audit_log_repository=AuditLogRepository(session),
        hardware_facade=_hardware_facade(),
    )


def _hardware_facade() -> HardwareFacade:
    return HardwareFacade(
        drum_controller=MockDrumAdapter(initial_position=0),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=MockRfidAdapter(),
    )


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _seed_api_authorization_domain(app) -> None:
    with app.state.session_factory() as session:
        _seed_authorization_domain(session)


def _seed_cli_authorization_domain(tmp_path: Path, sqlite_filename: str) -> None:
    from app.bootstrap import run_database_migrations

    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )
    run_database_migrations(settings)
    engine = create_engine(settings.database_url, future=True, connect_args={"check_same_thread": False})
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        _seed_authorization_domain(session)
    finally:
        session.close()
        engine.dispose()


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
