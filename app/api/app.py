from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.api.dependencies import get_application_container
from app.api.errors import register_exception_handlers
from app.api.schemas import (
    AuthResolveRequest,
    DispenseOperationRequest,
    ExportCreateRequest,
    RefillOperationRequest,
    ReturnOperationRequest,
    ServiceModeFinishRequest,
    ServiceModeStartRequest,
    to_api_payload,
)
from app.application.composition import ApplicationContainer
from app.application.dto.auth import AuthRequest
from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
from app.application.dto.query import (
    AuditLogListFilters,
    EventLogListFilters,
    ItemListFilters,
    OperationListFilters,
    Pagination,
    RecoveryCaseListFilters,
    SlotListFilters,
    UserListFilters,
)
from app.domain.enums import (
    ItemStatus,
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.bootstrap import bootstrap
from app.config import AppSettings, get_settings
from app.persistence.session import create_session_factory, create_sqlalchemy_engine


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = bootstrap(settings or get_settings())
    engine = create_sqlalchemy_engine(app_settings)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title=app_settings.app_name, lifespan=_lifespan)
    app.state.settings = app_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    register_exception_handlers(app)

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/readiness")
    def readiness(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.startup.run_startup_checks()))

    @app.post("/auth/resolve")
    def auth_resolve(
        payload: AuthResolveRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.auth.authorize(
            AuthRequest(
                user_id=payload.user_id,
                user_code=payload.user_code,
                allowed_roles=payload.allowed_roles,
            )
        )
        return JSONResponse(to_api_payload(dto))

    @app.get("/inventory/{slot_id}/{item_id}")
    def inventory_lookup(
        slot_id: int,
        item_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.inventory.lookup_inventory(slot_id=slot_id, item_id=item_id)))

    @app.post("/operations/dispense")
    def dispense_operation(
        payload: DispenseOperationRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.dispense.execute(
            DispenseRequest(
                user_id=payload.user_id,
                item_id=payload.item_id,
                slot_id=payload.slot_id,
                quantity=payload.quantity,
                session_id=payload.session_id,
            ),
            container.hardware.facade,
        )
        return JSONResponse(to_api_payload(dto))

    @app.post("/operations/return")
    def return_operation(
        payload: ReturnOperationRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.return_ops.execute(
            ReturnRequest(
                user_id=payload.user_id,
                item_id=payload.item_id,
                slot_id=payload.slot_id,
                quantity=payload.quantity,
                session_id=payload.session_id,
            ),
            container.hardware.facade,
        )
        return JSONResponse(to_api_payload(dto))

    @app.post("/operations/refill")
    def refill_operation(
        payload: RefillOperationRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.refill.execute(
            RefillRequest(
                operator_user_id=payload.operator_user_id,
                item_id=payload.item_id,
                slot_id=payload.slot_id,
                quantity=payload.quantity,
                mode=payload.mode,
                session_id=payload.session_id,
            ),
            container.hardware.facade,
        )
        return JSONResponse(to_api_payload(dto))

    @app.post("/recovery/scan")
    def recovery_scan(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.scan_recovery_targets()))

    @app.get("/users")
    def users_list(
        limit: int = 50,
        offset: int = 0,
        status: UserStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.queries.list_users(
            pagination=Pagination(limit=limit, offset=offset),
            filters=UserListFilters(status=status, created_from=created_from, created_to=created_to),
        )
        return JSONResponse(to_api_payload(result))

    @app.get("/items")
    def items_list(
        limit: int = 50,
        offset: int = 0,
        status: ItemStatus | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.queries.list_items(
            pagination=Pagination(limit=limit, offset=offset),
            filters=ItemListFilters(status=status),
        )
        return JSONResponse(to_api_payload(result))

    @app.get("/slots")
    def slots_list(
        limit: int = 50,
        offset: int = 0,
        status: SlotStatus | None = None,
        slot_type: SlotType | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.queries.list_slots(
            pagination=Pagination(limit=limit, offset=offset),
            filters=SlotListFilters(status=status, slot_type=slot_type),
        )
        return JSONResponse(to_api_payload(result))

    @app.get("/operations")
    def operations_list(
        limit: int = 50,
        offset: int = 0,
        state: OperationState | None = None,
        operation_type: OperationType | None = None,
        user_id: int | None = None,
        item_id: int | None = None,
        slot_id: int | None = None,
        session_id: int | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.queries.list_operations(
            pagination=Pagination(limit=limit, offset=offset),
            filters=OperationListFilters(
                operation_state=state,
                operation_type=operation_type,
                user_id=user_id,
                item_id=item_id,
                slot_id=slot_id,
                session_id=session_id,
            ),
        )
        return JSONResponse(to_api_payload(result))

    @app.get("/recovery/cases")
    def recovery_cases_list(
        limit: int = 50,
        offset: int = 0,
        status: RecoveryStatus | None = None,
        classification: RecoveryClassification | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.queries.list_recovery_cases(
            pagination=Pagination(limit=limit, offset=offset),
            filters=RecoveryCaseListFilters(
                status=status,
                classification=classification,
                created_from=created_from,
                created_to=created_to,
            ),
        )
        return JSONResponse(to_api_payload(result))

    @app.get("/recovery/cases/{recovery_case_id}")
    def recovery_case(
        recovery_case_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.get_case(recovery_case_id)))

    @app.get("/recovery/cases/{recovery_case_id}/manual-resolution")
    def recovery_manual_resolution(
        recovery_case_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.prepare_manual_resolution(recovery_case_id)))

    @app.get("/logs/events")
    def event_logs_list(
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.queries.list_event_logs(
            pagination=Pagination(limit=limit, offset=offset),
            filters=EventLogListFilters(
                event_type=event_type,
                created_from=created_from,
                created_to=created_to,
            ),
        )
        return JSONResponse(to_api_payload(result))

    @app.get("/logs/audit")
    def audit_logs_list(
        limit: int = 50,
        offset: int = 0,
        entity_type: str | None = None,
        action: str | None = None,
        reason_code: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.queries.list_audit_logs(
            pagination=Pagination(limit=limit, offset=offset),
            filters=AuditLogListFilters(
                entity_type=entity_type,
                action=action,
                reason_code=reason_code,
                created_from=created_from,
                created_to=created_to,
            ),
        )
        return JSONResponse(to_api_payload(result))

    @app.post("/service-mode/start")
    def service_mode_start(
        payload: ServiceModeStartRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.service_mode.enter_service_mode(
                    user_id=payload.user_id,
                    comment=payload.comment,
                )
            )
        )

    @app.post("/service-mode/finish")
    def service_mode_finish(
        payload: ServiceModeFinishRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.service_mode.exit_service_mode(
                    session_id=payload.session_id,
                    user_id=payload.user_id,
                    comment=payload.comment,
                )
            )
        )

    @app.post("/exports/create")
    def export_create(
        payload: ExportCreateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        snapshot = container.services.service_mode.get_hardware_snapshot(session_id=None)
        manifest = container.services.exports.build_diagnostic_dump_manifest(session_id=None, snapshot=snapshot)
        return JSONResponse(
            to_api_payload(
                container.services.exports.prepare_export(
                    requested_by_user_id=payload.requested_by_user_id,
                    destination_type=payload.destination_type,
                    destination_path=payload.destination_path,
                    diagnostic_manifest=manifest,
                    comment=payload.comment,
                )
            )
        )

    return app
