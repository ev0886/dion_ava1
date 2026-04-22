from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import get_application_container
from app.api.errors import register_exception_handlers
from app.api.schemas import (
    AdminNomenclatureCreateRequest,
    AdminNomenclatureUpdateRequest,
    AdminUserUpdateRequest,
    AuthReadAndResolveRfidRequest,
    AuthResolveRequest,
    DispenseOperationRequest,
    ExportCreateRequest,
    LocalUsbOperationsExportRequest,
    OperatorRemoveRequest,
    OperatorReplenishRequest,
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
from app.ui.mvp import render_admin_page, render_admin_touch_page, render_operator_page, render_user_page


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

    @app.get("/ui/user")
    def ui_user():
        return render_user_page(app.state.settings)

    @app.get("/ui/operator")
    def ui_operator():
        return render_operator_page(app.state.settings)

    @app.get("/ui/mvp")
    def ui_mvp():
        return render_user_page(app.state.settings)

    @app.get("/ui/admin")
    def ui_admin():
        return render_admin_page(app.state.settings)

    @app.get("/ui/admin-touch")
    def ui_admin_touch():
        return render_admin_touch_page(app.state.settings)

    @app.get("/local/usb/status")
    def local_usb_status(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(container.services.usb_storage.get_status_payload())

    @app.post("/local/usb/export/operations")
    def local_usb_export_operations(
        payload: LocalUsbOperationsExportRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.local_usb_exports.export_operations_csv(
                    date_from=payload.date_from,
                    date_to=payload.date_to,
                )
            )
        )

    @app.post("/local/usb/export/users")
    def local_usb_export_users(
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.local_usb_exports.export_users_csv()
            )
        )

    @app.post("/local/usb/export/balances")
    def local_usb_export_balances(
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.local_usb_exports.export_balances_csv()
            )
        )

    @app.post("/local/usb/import/users/check")
    def local_usb_import_users_check(
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.local_usb_exports.check_users_import_csv()
            )
        )

    @app.post("/local/usb/import/users")
    def local_usb_import_users(
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.local_usb_exports.import_users_csv()
            )
        )

    @app.get("/admin/users")
    def admin_list_users(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"users": to_api_payload(container.services.admin_users.list_users())})

    @app.get("/admin/nomenclature")
    def admin_list_nomenclature(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"nomenclature": to_api_payload(container.services.admin_nomenclature.list_nomenclature())})

    @app.get("/touch/nomenclature")
    def touch_list_nomenclature(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"nomenclature": to_api_payload(container.services.admin_nomenclature.list_active_nomenclature())})

    @app.post("/admin/nomenclature")
    def admin_create_nomenclature(
        payload: AdminNomenclatureCreateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.admin_nomenclature.create_nomenclature(name=payload.name)
        return JSONResponse(
            {
                "nomenclature": to_api_payload(result.record),
                "reactivated_existing": result.reactivated_existing,
            }
        )

    @app.put("/admin/nomenclature/{nomenclature_id}")
    def admin_update_nomenclature(
        nomenclature_id: int,
        payload: AdminNomenclatureUpdateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            {
                "nomenclature": to_api_payload(
                    container.services.admin_nomenclature.update_nomenclature(
                        nomenclature_id=nomenclature_id,
                        name=payload.name,
                    )
                )
            }
        )

    @app.post("/admin/nomenclature/{nomenclature_id}/activate")
    def admin_activate_nomenclature(
        nomenclature_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            {
                "nomenclature": to_api_payload(
                    container.services.admin_nomenclature.activate_nomenclature(nomenclature_id=nomenclature_id)
                )
            }
        )

    @app.post("/admin/nomenclature/{nomenclature_id}/deactivate")
    def admin_deactivate_nomenclature(
        nomenclature_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            {
                "nomenclature": to_api_payload(
                    container.services.admin_nomenclature.deactivate_nomenclature(nomenclature_id=nomenclature_id)
                )
            }
        )

    @app.get("/admin/operations/recent")
    def admin_list_recent_operations(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"operations": to_api_payload(container.services.admin_operations.list_recent_operations())})

    @app.get("/admin/operations/problem")
    def admin_list_problem_operations(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse({"operations": to_api_payload(container.services.admin_operations.list_problem_operations())})

    @app.get("/admin/operations/export")
    def admin_export_operations(
        date_from: date,
        date_to: date,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> Response:
        return Response(
            content=container.services.admin_operations.export_operations_csv(
                date_from=date_from,
                date_to=date_to,
            ).encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"content-disposition": 'attachment; filename="admin-operations-export.csv"'},
        )

    @app.get("/admin/system/status")
    def admin_system_status(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.admin_system_status.get_system_status(container.settings)))

    @app.get("/admin/users/export")
    def admin_export_users(container: ApplicationContainer = Depends(get_application_container)) -> Response:
        return Response(
            content=container.services.admin_users.export_users_csv().encode("utf-8-sig"),
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
                        is_active=payload.is_active,
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

    @app.get("/user/dispense-options")
    def user_dispense_options(
        user_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.user_dispense.list_options_for_user(user_id)))

    @app.get("/operator/board")
    def operator_board_state(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.inventory.get_operator_board_state()))

    @app.post("/operator/inventory/replenish")
    def operator_replenish(
        payload: OperatorReplenishRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.inventory.operator_replenish_slots(
                    operator_user_id=payload.operator_user_id,
                    nomenclature_id=payload.nomenclature_id,
                    slot_ids=payload.slot_ids,
                )
            )
        )

    @app.post("/operator/inventory/remove")
    def operator_remove(
        payload: OperatorRemoveRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.inventory.operator_remove_slots(
                    operator_user_id=payload.operator_user_id,
                    slot_ids=payload.slot_ids,
                )
            )
        )

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

    @app.post("/user/dispense")
    def user_dispense_operation(
        payload: DispenseOperationRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.user_dispense.dispense(
            DispenseRequest(
                user_id=payload.user_id,
                item_id=payload.item_id,
                slot_id=payload.slot_id,
                quantity=payload.quantity,
                session_id=payload.session_id,
            )
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
