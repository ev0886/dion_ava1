from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.admin_service import AdminOperationService, AdminSystemStatusService, AdminUserService
from app.application.auth_service import AuthService
from app.application.dispense_service import DispenseOperationService
from app.application.export_service import ExportService
from app.application.inventory_service import InventoryService
from app.application.recovery_service import RecoveryService
from app.application.refill_service import RefillOperationService
from app.application.return_service import ReturnOperationService
from app.application.service_mode_service import ServiceModeService
from app.application.startup_service import StartupOrchestrationService
from app.application.session_service import OperationSessionService
from app.application.usb_storage_service import UsbStorageDiscoveryService
from app.bootstrap import bootstrap
from app.config import AppSettings, get_settings
from app.hardware import HardwareBundle, create_hardware_bundle
from app.hardware.transport_config import DrumHardwareEndpointTransportConfig
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository, OperationSessionRepository
from app.persistence.repositories.recovery import RecoveryRepository
from app.persistence.repositories.service import ExportRepository
from app.persistence.repositories.users import UserRepository
from app.persistence.session import create_session_factory, create_sqlalchemy_engine


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    users: UserRepository
    inventory: InventoryRepository
    operations: OperationRepository
    operation_sessions: OperationSessionRepository
    recovery: RecoveryRepository
    event_logs: EventLogRepository
    audit_logs: AuditLogRepository
    exports: ExportRepository


@dataclass(frozen=True, slots=True)
class ServiceBundle:
    admin_users: AdminUserService
    admin_operations: AdminOperationService
    admin_system_status: AdminSystemStatusService
    auth: AuthService
    inventory: InventoryService
    operation_sessions: OperationSessionService
    dispense: DispenseOperationService
    return_ops: ReturnOperationService
    refill: RefillOperationService
    recovery: RecoveryService
    service_mode: ServiceModeService
    exports: ExportService
    startup: StartupOrchestrationService
    usb_storage: UsbStorageDiscoveryService


@dataclass(slots=True)
class ApplicationContainer:
    settings: AppSettings
    engine: Engine
    session_factory: sessionmaker[Session]
    session: Session
    repositories: RepositoryBundle
    hardware: HardwareBundle
    services: ServiceBundle

    def close(self) -> None:
        self.session.close()
        self.engine.dispose()


def build_repositories(session: Session) -> RepositoryBundle:
    return RepositoryBundle(
        users=UserRepository(session),
        inventory=InventoryRepository(session),
        operations=OperationRepository(session),
        operation_sessions=OperationSessionRepository(session),
        recovery=RecoveryRepository(session),
        event_logs=EventLogRepository(session),
        audit_logs=AuditLogRepository(session),
        exports=ExportRepository(session),
    )


def build_services(
    *,
    settings: AppSettings,
    session: Session,
    repositories: RepositoryBundle,
    hardware: HardwareBundle,
) -> ServiceBundle:
    auth_service = AuthService(repositories.users)
    inventory_service = InventoryService(repositories.inventory)
    operation_session_service = OperationSessionService(repositories.operation_sessions)
    recovery_service = RecoveryService(
        repositories.recovery,
        repositories.operations,
        repositories.inventory,
    )
    startup_service = StartupOrchestrationService(
        db_session=session,
        hardware_facade=hardware.facade,
        recovery_service=recovery_service,
    )
    return ServiceBundle(
        admin_users=AdminUserService(repositories.users),
        admin_operations=AdminOperationService(repositories.operations),
        admin_system_status=AdminSystemStatusService(startup_service),
        auth=auth_service,
        inventory=inventory_service,
        operation_sessions=operation_session_service,
        dispense=DispenseOperationService(
            repositories.operations,
            repositories.inventory,
            post_move_unlock_delay_ms=_resolve_dispense_post_move_unlock_delay_ms(settings),
        ),
        return_ops=ReturnOperationService(repositories.operations, repositories.inventory),
        refill=RefillOperationService(
            repositories.operations,
            repositories.inventory,
            repositories.operation_sessions,
        ),
        recovery=recovery_service,
        service_mode=ServiceModeService(
            auth_service=auth_service,
            session_repository=repositories.operation_sessions,
            event_log_repository=repositories.event_logs,
            audit_log_repository=repositories.audit_logs,
            hardware_facade=hardware.facade,
        ),
        exports=ExportService(
            export_repository=repositories.exports,
            event_log_repository=repositories.event_logs,
            audit_log_repository=repositories.audit_logs,
        ),
        startup=startup_service,
        usb_storage=UsbStorageDiscoveryService(),
    )


def build_application_container(
    *,
    settings: AppSettings,
    engine: Engine,
    session_factory: sessionmaker[Session],
    session: Session,
) -> ApplicationContainer:
    repositories = build_repositories(session)
    hardware = create_hardware_bundle(settings)
    services = build_services(settings=settings, session=session, repositories=repositories, hardware=hardware)
    return ApplicationContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        session=session,
        repositories=repositories,
        hardware=hardware,
        services=services,
    )


def create_bootstrapped_application_container(settings: AppSettings | None = None) -> ApplicationContainer:
    app_settings = bootstrap(settings or get_settings())
    engine = create_sqlalchemy_engine(app_settings)
    session_factory = create_session_factory(engine)
    session = session_factory()
    return build_application_container(
        settings=app_settings,
        engine=engine,
        session_factory=session_factory,
        session=session,
    )


def _resolve_dispense_post_move_unlock_delay_ms(settings: AppSettings) -> int:
    raw_drum_config = settings.hardware_real_endpoints.get("drum_controller")
    if raw_drum_config is None:
        return 0

    try:
        drum_config = DrumHardwareEndpointTransportConfig.model_validate(raw_drum_config)
    except ValidationError:
        return 0

    return drum_config.protocol.post_move_unlock_delay_ms
