from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import get_application_container
from app.api.errors import register_exception_handlers
from app.api.schemas import (
    AdminUserUpdateRequest,
    AuthReadAndResolveRfidRequest,
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
from app.bootstrap import bootstrap
from app.config import AppSettings, get_settings
from app.persistence.session import create_session_factory, create_sqlalchemy_engine
from app.ui.mvp import render_admin_page, render_mvp_page


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
    app.mount("/ui-assets", StaticFiles(directory=Path(__file__).resolve().parent.parent / "ui" / "static"), name="ui-assets")

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/ui/mvp")
    def ui_mvp():
        return render_mvp_page(app.state.settings)

    @app.get("/ui/admin")
    def ui_admin():
        return render_admin_page(app.state.settings)

    @app.get("/admin/users")
    def admin_list_users(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"users": to_api_payload(container.services.admin_users.list_users())})

    @app.get("/admin/operations/recent")
    def admin_list_recent_operations(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"operations": to_api_payload(container.services.admin_operations.list_recent_operations())})

    @app.get("/admin/operations/problem")
    def admin_list_problem_operations(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"operations": to_api_payload(container.services.admin_operations.list_problem_operations())})

    @app.get("/admin/users/export")
    def admin_export_users(container: ApplicationContainer = Depends(get_application_container)) -> PlainTextResponse:
        return PlainTextResponse(
            content=container.services.admin_users.export_users_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"content-disposition": 'attachment; filename="admin-users-export.csv"'},
        )

    @app.put("/admin/users/{user_id}")
    def admin_update_user(
        user_id: int,
        payload: AdminUserUpdateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            {
                "user": to_api_payload(
                    container.services.admin_users.update_user(
                        user_id=user_id,
                        rfid_uid=payload.rfid_uid,
                        dispense_restriction_policy=payload.dispense_restriction_policy,
                    )
                )
            }
        )

    @app.post("/admin/users/import")
    async def admin_import_users(
        request: Request,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        csv_text = (await request.body()).decode("utf-8-sig")
        return JSONResponse(
            {
                "result": to_api_payload(
                    container.services.admin_users.import_users_csv(csv_text)
                )
            }
        )

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

    @app.post("/auth/read-and-resolve-rfid")
    def auth_read_and_resolve_rfid(
        payload: AuthReadAndResolveRfidRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.auth.read_and_resolve_rfid(
            hardware_facade=container.hardware.facade,
            allowed_roles=payload.allowed_roles,
        )
        return JSONResponse(to_api_payload(dto))

    @app.get("/inventory/{slot_id}/{item_id}")
    def inventory_lookup(
        slot_id: int,
        item_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.inventory.lookup_inventory(slot_id=slot_id, item_id=item_id)))

    @app.get("/inventory/available-dispense-options")
    def available_dispense_options(
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.inventory.list_available_dispense_options()))

    @app.get("/inventory/kiosk-dispense-options")
    def kiosk_dispense_options(
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.inventory.list_kiosk_dispense_options()))

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
