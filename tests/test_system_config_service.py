from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.auth_service import AuthService
from app.application.dto.system_config import SystemConfigPatchDTO
from app.application.exceptions import ValidationError
from app.application.system_config_service import SystemConfigService
from app.config import AppSettings, HardwareProvider
from app.domain.enums import RoleCode, UserStatus
from app.persistence.base import Base
from app.persistence.models import AuditLog, Role, SystemSetting, User
from app.persistence.repositories.logs import AuditLogRepository
from app.persistence.repositories.service import SystemSettingRepository
from app.persistence.repositories.users import UserRepository


def test_get_effective_config_happy_path(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    with session_factory() as session:
        _seed_operator(session)
        service = _system_config_service(session, tmp_path)

        config = service.get_effective_config()

        assert config.hardware.provider.value == "mock"
        assert config.hardware.provider.source == "default"
        assert config.hardware.real_endpoints[0].endpoint_name == "drum_controller"
        assert config.hardware.real_endpoints[0].location == "COM7"
        assert config.hardware.real_endpoints[1].location == "127.0.0.1:9001"
        assert config.export.default_destination_path.value == "var/exports"
        assert config.storage.sqlite_filename == "system_config.sqlite3"


def test_safe_config_update_happy_path(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    with session_factory() as session:
        operator_user_id = _seed_operator(session)
        service = _system_config_service(session, tmp_path)

        result = service.apply_overrides(
            SystemConfigPatchDTO(
                actor_user_id=operator_user_id,
                provided_fields=frozenset({"hardware_provider", "export_default_destination_path"}),
                hardware_provider=HardwareProvider.REAL,
                export_default_destination_path="var/ops-exports",
                comment="switch provider for maintenance",
            )
        )

        assert result.hardware.provider.value == "real"
        assert result.hardware.provider.source == "override"
        assert result.export.default_destination_path.value == "var/ops-exports"
        assert service.runtime_settings.hardware_provider is HardwareProvider.REAL
        persisted_keys = {row.key: row.value for row in session.execute(select(SystemSetting)).scalars()}
        assert "hardware.provider" in persisted_keys


def test_invalid_config_update_rejected(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    with session_factory() as session:
        operator_user_id = _seed_operator(session)
        service = _system_config_service(session, tmp_path)

        with pytest.raises(ValidationError):
            service.apply_overrides(
                SystemConfigPatchDTO(
                    actor_user_id=operator_user_id,
                    provided_fields=frozenset({"export_default_destination_type"}),
                    export_default_destination_type="network-share",
                )
            )


def test_config_update_creates_audit_log(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    with session_factory() as session:
        operator_user_id = _seed_operator(session)
        service = _system_config_service(session, tmp_path)

        service.apply_overrides(
            SystemConfigPatchDTO(
                actor_user_id=operator_user_id,
                provided_fields=frozenset({"export_default_destination_path"}),
                export_default_destination_path="var/audit-exports",
                comment="update export path",
            )
        )

        audit_logs = session.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
        assert len(audit_logs) == 1
        assert audit_logs[0].action == "system_config_update"
        assert audit_logs[0].before_json == {
            "hardware_provider": "mock",
            "export_default_destination_type": "filesystem",
            "export_default_destination_path": "var/exports",
        }
        assert audit_logs[0].after_json == {
            "hardware_provider": "mock",
            "export_default_destination_type": "filesystem",
            "export_default_destination_path": "var/audit-exports",
        }


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="system_config.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM7"),
            "lock_controller": _tcp_endpoint_config(
                code="lock-1",
                driver_name="lock-driver",
                host="127.0.0.1",
                port=9001,
            ),
        },
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


def _seed_operator(session: Session) -> int:
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add(operator_role)
    session.flush()
    operator = User(
        role_id=operator_role.id,
        user_code="operator-1",
        full_name="Operator One",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    session.add(operator)
    session.commit()
    return operator.id


def _system_config_service(session: Session, tmp_path: Path) -> SystemConfigService:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="system_config.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.MOCK,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM7"),
            "lock_controller": _tcp_endpoint_config(
                code="lock-1",
                driver_name="lock-driver",
                host="127.0.0.1",
                port=9001,
            ),
        },
    )
    return SystemConfigService(
        runtime_settings=settings,
        auth_service=AuthService(UserRepository(session)),
        system_setting_repository=SystemSettingRepository(session),
        audit_log_repository=AuditLogRepository(session),
    )


def _serial_endpoint_config(*, code: str, driver_name: str, port: str) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 9600,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }


def _tcp_endpoint_config(*, code: str, driver_name: str, host: str, port: int) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "transport": {
            "transport": "tcp",
            "host": host,
            "port": port,
        },
    }
