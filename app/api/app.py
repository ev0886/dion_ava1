from __future__ import annotations

from contextlib import asynccontextmanager

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
from app.application.dto.logs import AuditLogQueryFilters, EventLogQueryFilters
from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
from app.application.dto.operations import OperationQueryFilters
from app.application.dto.recovery import RecoveryCaseQueryFilters
from app.domain.enums import OperationState, OperationType, RecoveryClassification, RecoveryStatus
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

    @app.get("/operations")
    def list_operations(
        operation_type: OperationType | None = None,
        operation_state: OperationState | None = None,
        user_id: int | None = None,
        item_id: int | None = None,
        slot_id: int | None = None,
        session_id: int | None = None,
        limit: int = 100,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.operations_query.list_operations(
            OperationQueryFilters(
                operation_type=operation_type,
                operation_state=operation_state,
                user_id=user_id,
                item_id=item_id,
                slot_id=slot_id,
                session_id=session_id,
                limit=limit,
            )
        )
        return JSONResponse(to_api_payload(dto))

    @app.get("/operations/{operation_id}")
    def operation_detail(
        operation_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.operations_query.get_operation(operation_id)))

    @app.get("/operations/{operation_id}/history")
    def operation_history(
        operation_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.operations_query.get_operation_history(operation_id)))

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

    @app.get("/recovery/cases")
    def recovery_case_list(
        status: RecoveryStatus | None = None,
        classification: RecoveryClassification | None = None,
        limit: int = 100,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.recovery.list_cases(
                    RecoveryCaseQueryFilters(
                        status=status,
                        classification=classification,
                        limit=limit,
                    )
                )
            )
        )

    @app.get("/recovery/cases/{recovery_case_id}")
    def recovery_case(
        recovery_case_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.get_case_detail(recovery_case_id)))

    @app.get("/recovery/cases/{recovery_case_id}/manual-resolution")
    def recovery_manual_resolution(
        recovery_case_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.prepare_manual_resolution(recovery_case_id)))

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

    @app.get("/audit-logs")
    def list_audit_logs(
        entity_type: str | None = None,
        actor_user_id: int | None = None,
        limit: int = 100,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.logs_query.list_audit_logs(
                    AuditLogQueryFilters(
                        entity_type=entity_type,
                        actor_user_id=actor_user_id,
                        limit=limit,
                    )
                )
            )
        )

    @app.get("/event-logs")
    def list_event_logs(
        event_type: str | None = None,
        level: str | None = None,
        limit: int = 100,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.logs_query.list_event_logs(
                    EventLogQueryFilters(
                        event_type=event_type,
                        level=level,
                        limit=limit,
                    )
                )
            )
        )

    return app
