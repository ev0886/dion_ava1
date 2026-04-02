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
    ItemCreateRequest,
    ItemUpdateRequest,
    ItemListQuery,
    PermissionAssignRequest,
    PermissionRevokeRequest,
    RefillOperationRequest,
    ReturnOperationRequest,
    ServiceModeFinishRequest,
    ServiceModeStartRequest,
    UserCreateRequest,
    UserListQuery,
    UserUpdateRequest,
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

    @app.post("/users")
    def create_user(
        payload: UserCreateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.users.create_user(
            user_code=payload.user_code,
            full_name=payload.full_name,
            role_id=payload.role_id,
            actor_user_id=payload.actor_user_id,
            comment=payload.comment,
        )
        return JSONResponse(to_api_payload(result))

    @app.patch("/users/{user_id}")
    def update_user(
        user_id: int,
        payload: UserUpdateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        if payload.is_active is not None:
            result = container.services.users.set_user_active(
                user_id=user_id,
                is_active=payload.is_active,
                actor_user_id=payload.actor_user_id,
                comment=payload.comment,
            )
        else:
            result = container.services.users.update_user(
                user_id=user_id,
                user_code=payload.user_code,
                full_name=payload.full_name,
                role_id=payload.role_id,
                actor_user_id=payload.actor_user_id,
                comment=payload.comment,
            )
        return JSONResponse(to_api_payload(result))

    @app.get("/users/{user_id}")
    def get_user(
        user_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.users.get_user_details(user_id)))

    @app.get("/users")
    def list_users(
        role_id: int | None = None,
        status: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        query = UserListQuery(role_id=role_id, status=status, is_active=is_active, search=search)
        return JSONResponse(
            to_api_payload(
                container.services.users.list_users(
                    role_id=query.role_id,
                    status=query.status,
                    is_active=query.is_active,
                    search=query.search,
                )
            )
        )

    @app.post("/items")
    def create_item(
        payload: ItemCreateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.items.create_item(
            sku=payload.sku,
            name=payload.name,
            unit=payload.unit,
            item_group_id=payload.item_group_id,
            description=payload.description,
            return_allowed=payload.return_allowed,
            min_level=payload.min_level,
            actor_user_id=payload.actor_user_id,
            comment=payload.comment,
        )
        return JSONResponse(to_api_payload(result))

    @app.patch("/items/{item_id}")
    def update_item(
        item_id: int,
        payload: ItemUpdateRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        if payload.is_active is not None:
            result = container.services.items.set_item_active(
                item_id=item_id,
                is_active=payload.is_active,
                actor_user_id=payload.actor_user_id,
                comment=payload.comment,
            )
        else:
            result = container.services.items.update_item(
                item_id=item_id,
                sku=payload.sku,
                name=payload.name,
                unit=payload.unit,
                item_group_id=payload.item_group_id,
                description=payload.description,
                return_allowed=payload.return_allowed,
                min_level=payload.min_level,
                actor_user_id=payload.actor_user_id,
                comment=payload.comment,
            )
        return JSONResponse(to_api_payload(result))

    @app.get("/items/{item_id}")
    def get_item(
        item_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.items.get_item_details(item_id)))

    @app.get("/items")
    def list_items(
        item_group_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        query = ItemListQuery(item_group_id=item_group_id, status=status, search=search)
        return JSONResponse(
            to_api_payload(
                container.services.items.list_items(
                    item_group_id=query.item_group_id,
                    status=query.status,
                    search=query.search,
                )
            )
        )

    @app.post("/permissions")
    def assign_permission(
        payload: PermissionAssignRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        result = container.services.permissions.assign_permission(
            user_id=payload.user_id,
            item_id=payload.item_id,
            item_group_id=payload.item_group_id,
            can_dispense=payload.can_dispense,
            can_return=payload.can_return,
            actor_user_id=payload.actor_user_id,
            comment=payload.comment,
        )
        return JSONResponse(to_api_payload(result))

    @app.delete("/permissions/{permission_id}")
    def revoke_permission(
        permission_id: int,
        payload: PermissionRevokeRequest,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.permissions.revoke_permission(
                    permission_id=permission_id,
                    actor_user_id=payload.actor_user_id,
                    comment=payload.comment,
                )
            )
        )

    @app.get("/users/{user_id}/permissions")
    def list_user_permissions(
        user_id: int,
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.permissions.list_permissions_for_user(user_id)))

    return app
