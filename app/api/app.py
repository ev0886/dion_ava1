from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, Path
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.dependencies import get_application_container
from app.api.errors import register_exception_handlers
from app.api.schemas import (
    AuthReadResolveRfidRequest,
    AuthResolveRequest,
    DispenseOperationRequest,
    ErrorResponse,
    ExportCreateRequest,
    RecoveryManualResolutionRequest,
    RefillOperationRequest,
    ReturnOperationRequest,
    ServiceModeFinishRequest,
    ServiceModeStartRequest,
    to_api_payload,
)
from app.application.composition import ApplicationContainer
from app.application.dto.auth import AuthRequest
from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
from app.application.dto.recovery import ManualResolutionRequestDTO
from app.bootstrap import bootstrap
from app.config import AppSettings, get_settings
from app.persistence.session import create_session_factory, create_sqlalchemy_engine
from app.ui.operator_page import render_operator_page


_LIVE_RFID_READ_TIMEOUT_MS = 5000


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

    @app.get("/operator", include_in_schema=False)
    def operator_ui() -> HTMLResponse:
        return HTMLResponse(render_operator_page())

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/readiness")
    def readiness(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.startup.run_startup_checks()))

    @app.post(
        "/auth/resolve",
        summary="Resolve an operator or user identity",
        description=(
            "Use this first when the operator needs to confirm who is about to interact with the stand. "
            "Provide exactly one of user_id, user_code, or rfid_uid. Demo-seeded values include user_id 3, "
            'user_code "user-1", operator user_code "operator-1", and RFID UID "DEMO-USER-1".'
        ),
    )
    def auth_resolve(
        payload: AuthResolveRequest = Body(
            openapi_examples={
                "by_user_id": {
                    "summary": "Resolve the seeded demo user by ID",
                    "value": {"user_id": 3},
                },
                "by_user_code": {
                    "summary": "Resolve the seeded demo user by code",
                    "value": {"user_code": "user-1"},
                },
                "by_rfid_uid": {
                    "summary": "Resolve the seeded demo user by RFID UID",
                    "value": {"rfid_uid": "DEMO-USER-1"},
                },
                "operator_only": {
                    "summary": "Resolve only if the identity is an operator",
                    "value": {"user_code": "operator-1", "allowed_roles": ["operator"]},
                },
            }
        ),
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        dto = container.services.auth.authorize(
            AuthRequest(
                user_id=payload.user_id,
                user_code=payload.user_code,
                rfid_uid=payload.rfid_uid,
                allowed_roles=payload.allowed_roles,
            )
        )
        return JSONResponse(to_api_payload(dto))

    @app.post(
        "/auth/read-and-resolve-rfid",
        summary="Read one RFID card from hardware and resolve it to a user",
        description=(
            "Use this when the backend should read the next RFID card from the configured reader and immediately "
            "return the same resolved user payload as /auth/resolve."
        ),
    )
    def auth_read_and_resolve_rfid(
        payload: AuthReadResolveRfidRequest = Body(
            default=AuthReadResolveRfidRequest(),
            openapi_examples={
                "default": {
                    "summary": "Read from hardware and resolve any active user",
                    "value": {},
                },
                "operator_only": {
                    "summary": "Require the scanned card to belong to an operator",
                    "value": {"allowed_roles": ["operator"]},
                },
            },
        ),
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        read_result = container.hardware.facade.read_rfid_card(timeout_ms=_LIVE_RFID_READ_TIMEOUT_MS)
        dto = container.services.auth.authorize(
            AuthRequest(
                rfid_uid=read_result.uid,
                allowed_roles=payload.allowed_roles,
            )
        )
        return JSONResponse(to_api_payload(dto))

    @app.get(
        "/inventory/slots/{slot_id}/items/{item_id}",
        summary="Check slot inventory for an item",
        description=(
            "Use this to confirm the seeded slot and item combination before a demo or operator action. "
            "Demo stand example: slot_id 1 with item_id 1."
        ),
    )
    def inventory_lookup(
        slot_id: int = Path(description="Physical slot ID. Demo stand example: 1."),
        item_id: int = Path(description="Item ID expected in the slot. Demo stand example: 1."),
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.inventory.lookup_inventory(slot_id=slot_id, item_id=item_id)))

    @app.post(
        "/operations/dispense",
        summary="Dispense an item to a user",
        description=(
            "Operator-tested happy path: resolve the user, optionally inspect inventory, then execute this request. "
            "Use session_id null or omit it entirely when no service session is active."
        ),
    )
    def dispense_operation(
        payload: DispenseOperationRequest = Body(
            openapi_examples={
                "default": {
                    "summary": "Happy path from the seeded stand",
                    "value": {"user_id": 3, "item_id": 1, "slot_id": 1, "quantity": 1},
                },
                "with_null_session": {
                    "summary": "Explicitly send null session_id",
                    "value": {"user_id": 3, "item_id": 1, "slot_id": 1, "quantity": 1, "session_id": None},
                }
            }
        ),
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

    @app.post(
        "/operations/return",
        summary="Return an item from a user",
        description=(
            "Operator-tested happy path: use the seeded user and item, and leave session_id null or omitted unless "
            "you are already working inside a real service session. slot_id may stay null when the backend should "
            "resolve it automatically."
        ),
    )
    def return_operation(
        payload: ReturnOperationRequest = Body(
            openapi_examples={
                "default": {
                    "summary": "Happy path with automatic slot resolution",
                    "value": {"user_id": 3, "item_id": 1, "quantity": 1},
                },
                "with_null_slot_and_session": {
                    "summary": "Explicit null slot_id and session_id",
                    "value": {"user_id": 3, "item_id": 1, "slot_id": None, "quantity": 1, "session_id": None},
                }
            }
        ),
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

    refill_route_kwargs = {
        "summary": "Refill inventory for a slot",
        "description": (
            "Use this for service/operator restocking. If session_id is null or omitted, the backend can create or "
            "resolve the service-session flow automatically."
        ),
    }

    @app.post("/operations/refill-item", include_in_schema=False)
    @app.post("/operations/refill", **refill_route_kwargs)
    def refill_operation(
        payload: RefillOperationRequest = Body(
            openapi_examples={
                "default": {
                    "summary": "Set the seeded slot balance using the demo operator",
                    "value": {
                        "operator_user_id": 2,
                        "item_id": 1,
                        "slot_id": 1,
                        "quantity": 5,
                        "mode": "set",
                    },
                },
                "with_null_session": {
                    "summary": "Explicitly allow the backend to create or reuse the service session",
                    "value": {
                        "operator_user_id": 2,
                        "item_id": 1,
                        "slot_id": 1,
                        "quantity": 5,
                        "mode": "set",
                        "session_id": None,
                    },
                }
            }
        ),
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

    @app.post(
        "/recovery/scan",
        summary="Scan for recovery candidates",
        description=(
            "Run this first when investigating incomplete or stuck operations. On the demo stand with recovery seed "
            "enabled, this can produce recovery_case_id 1."
        ),
    )
    def recovery_scan(container: ApplicationContainer = Depends(get_application_container)) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.scan_recovery_targets()))

    @app.get(
        "/recovery/cases/{recovery_case_id}",
        summary="Read a recovery case",
        description="Use recovery_case_id from /recovery/scan. Demo recovery example: recovery_case_id 1.",
        responses={
            404: {"model": ErrorResponse, "description": "Recovery case was not found."},
        },
    )
    def recovery_case(
        recovery_case_id: int = Path(description="Recovery case ID from /recovery/scan. Demo example: 1."),
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.get_case(recovery_case_id)))

    @app.get(
        "/recovery/cases/{recovery_case_id}/manual-resolution",
        summary="Prepare manual recovery resolution",
        description=(
            "Use this after reading the case details and before posting a manual decision. It returns the impacted "
            "entities and current case context the operator should verify physically."
        ),
        responses={
            404: {"model": ErrorResponse, "description": "Recovery case was not found."},
        },
    )
    def recovery_manual_resolution(
        recovery_case_id: int = Path(description="Recovery case ID to inspect for operator resolution. Demo example: 1."),
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(to_api_payload(container.services.recovery.prepare_manual_resolution(recovery_case_id)))

    @app.post(
        "/recovery/cases/{recovery_case_id}/manual-resolution",
        summary="Apply manual recovery resolution",
        description=(
            "Typical operator flow: scan for cases, inspect the case, review this preparation endpoint, then post a "
            'decision such as "close_case" with an operator comment.'
        ),
        responses={
            404: {"model": ErrorResponse, "description": "Recovery case was not found."},
            409: {"model": ErrorResponse, "description": "Recovery case cannot be manually resolved in its current state."},
        },
    )
    def recovery_manual_resolution_apply(
        recovery_case_id: int = Path(description="Recovery case ID to resolve manually. Demo example: 1."),
        payload: RecoveryManualResolutionRequest = Body(
            openapi_examples={
                "default": {
                    "summary": "Close the demo recovery case after physical verification",
                    "value": {
                        "operator_user_id": 2,
                        "decision": "close_case",
                        "comment": "Operator verified physical state",
                    },
                }
            }
        ),
        container: ApplicationContainer = Depends(get_application_container),
    ) -> JSONResponse:
        return JSONResponse(
            to_api_payload(
                container.services.recovery.resolve_manual_case(
                    recovery_case_id,
                    ManualResolutionRequestDTO(
                        operator_user_id=payload.operator_user_id,
                        decision=payload.decision,
                        comment=payload.comment,
                    ),
                )
            )
        )

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
