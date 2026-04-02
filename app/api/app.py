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
    InventoryAdjustmentRequest,
    RefillOperationRequest,
    ReturnOperationRequest,
    ServiceModeFinishRequest,
    ServiceModeStartRequest,
    SlotBindingCreateRequest,
    SlotCreateRequest,
    SlotUpdateRequest,
    to_api_payload,
)
from app.application.composition import ApplicationContainer
from app.application.dto.auth import AuthRequest
from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
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

    @app.post("/slots")
    def create_slot(
        payload: SlotCreateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.slots.create_slot(
            code=payload.code,
            slot_type=payload.slot_type,
            drum_position=payload.drum_position,
            board_address=payload.board_address,
            lock_number=payload.lock_number,
            capacity=payload.capacity,
            status=payload.status,
            actor_user_id=payload.actor_user_id,
            reason_code=payload.reason_code,
            comment=payload.comment,
        )
        return JSONResponse(to_api_payload(dto))

    @app.patch("/slots/{slot_id}")
    def update_slot(
        slot_id: int,
        payload: SlotUpdateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        if payload.is_active is True:
            dto = container.services.slots.activate_slot(
                slot_id=slot_id,
                actor_user_id=payload.actor_user_id,
                reason_code=payload.reason_code,
                comment=payload.comment,
            )
        elif payload.is_active is False:
            dto = container.services.slots.deactivate_slot(
                slot_id=slot_id,
                actor_user_id=payload.actor_user_id,
                reason_code=payload.reason_code,
                comment=payload.comment,
            )
        else:
            dto = container.services.slots.update_slot(
                slot_id=slot_id,
                code=payload.code,
                slot_type=payload.slot_type,
                drum_position=payload.drum_position,
                board_address=payload.board_address,
                lock_number=payload.lock_number,
                capacity=payload.capacity,
                status=payload.status,
                actor_user_id=payload.actor_user_id,
                reason_code=payload.reason_code,
                comment=payload.comment,
            )
        return JSONResponse(to_api_payload(dto))

    @app.get("/slots/{slot_id}")
    def get_slot(
        slot_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.slots.get_slot_details(slot_id)))

    @app.get("/slots")
    def list_slots(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.slots.list_slots()))

    @app.post("/slot-bindings")
    def create_slot_binding(
        payload: SlotBindingCreateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.slots.create_binding(
            slot_id=payload.slot_id,
            item_id=payload.item_id,
            binding_type=payload.binding_type,
            actor_user_id=payload.actor_user_id,
            reason_code=payload.reason_code,
            comment=payload.comment,
        )
        return JSONResponse(to_api_payload(dto))

    @app.delete("/slot-bindings/{binding_id}")
    def deactivate_slot_binding(
        binding_id: int,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.slots.deactivate_binding(
            binding_id=binding_id,
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
        )
        return JSONResponse(to_api_payload(dto))

    @app.get("/slots/{slot_id}/bindings")
    def list_slot_bindings(
        slot_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.slots.list_bindings_for_slot(slot_id)))

    @app.get("/items/{item_id}/bindings")
    def list_item_bindings(
        item_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.slots.list_bindings_for_item(item_id)))

    @app.get("/inventory-balances")
    def list_inventory_balances(
        slot_id: int | None = None,
        item_id: int | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.inventory.list_balances(slot_id=slot_id, item_id=item_id)))

    @app.post("/inventory-adjustments")
    def inventory_adjustments(
        payload: InventoryAdjustmentRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        if payload.mode == "delta":
            dto = container.services.inventory_admin.adjust_inventory(
                slot_id=payload.slot_id,
                item_id=payload.item_id,
                quantity_delta=payload.quantity,
                actor_user_id=payload.actor_user_id,
                reason_code=payload.reason_code,
                comment=payload.comment,
            )
        else:
            dto = container.services.inventory_admin.set_inventory(
                slot_id=payload.slot_id,
                item_id=payload.item_id,
                quantity=payload.quantity,
                actor_user_id=payload.actor_user_id,
                reason_code=payload.reason_code,
                comment=payload.comment,
            )
        return JSONResponse(to_api_payload(dto))

    return app
