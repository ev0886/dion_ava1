from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.application.composition import ApplicationContainer
from app.application.dto.auth import AuthRequest, AuthenticatedUserDTO
from app.application.exceptions import ActorConflictError, AuthenticationError, AuthorizationError
from app.domain.enums import RoleCode
from app.persistence.models import AuditLog

from .dependencies import get_application_container

_bearer_scheme = HTTPBearer(auto_error=False)
_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_DEV_TOKEN_PREFIX = "dev-token:"


@dataclass(frozen=True, slots=True)
class RequestActor:
    user: AuthenticatedUserDTO
    credential_kind: str


def require_actor(
    *,
    allowed_roles: tuple[RoleCode, ...] = (),
) -> Callable[..., RequestActor]:
    def _dependency(
        request: Request,
        container: ApplicationContainer = Depends(get_application_container),
        bearer: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
        api_key: str | None = Depends(_api_key_scheme),
    ) -> RequestActor:
        return _authenticate_request(
            request=request,
            container=container,
            allowed_roles=allowed_roles,
            bearer=bearer,
            api_key=api_key,
        )

    return _dependency


def resolve_request_actor_id(actor: RequestActor, payload_actor_id: int | None, *, field_name: str) -> int:
    if payload_actor_id is None:
        return actor.user.user_id
    if payload_actor_id != actor.user.user_id:
        raise ActorConflictError(
            f"{field_name} does not match authenticated actor",
        )
    return actor.user.user_id


def _authenticate_request(
    *,
    request: Request,
    container: ApplicationContainer,
    allowed_roles: tuple[RoleCode, ...],
    bearer: HTTPAuthorizationCredentials | None,
    api_key: str | None,
) -> RequestActor:
    token, credential_kind = _extract_token(bearer=bearer, api_key=api_key)
    user_code = _resolve_user_code(
        container.settings.auth_static_tokens,
        token,
        allow_default_dev_tokens=container.settings.auth_enable_default_dev_tokens,
    )
    if user_code is None:
        _record_auth_audit(request, actor_user_id=None, action="authentication_failed", comment="Invalid API credential")
        raise AuthenticationError("Invalid credentials")
    try:
        user = container.services.auth.authorize(AuthRequest(user_code=user_code, allowed_roles=allowed_roles))
    except AuthorizationError as error:
        _record_auth_audit(
            request,
            actor_user_id=None,
            action="authorization_failed",
            comment=str(error),
        )
        raise
    except Exception as error:
        _record_auth_audit(
            request,
            actor_user_id=None,
            action="authentication_failed",
            comment=str(error),
        )
        raise
    return RequestActor(user=user, credential_kind=credential_kind)


def _extract_token(
    *,
    bearer: HTTPAuthorizationCredentials | None,
    api_key: str | None,
) -> tuple[str, str]:
    bearer_token = None
    if bearer is not None:
        if bearer.scheme.lower() != "bearer":
            raise AuthenticationError("Authorization header must use Bearer scheme")
        bearer_token = bearer.credentials.strip()
        if not bearer_token:
            raise AuthenticationError("Bearer token is empty")

    api_key_token = api_key.strip() if api_key is not None else None
    if api_key_token == "":
        raise AuthenticationError("API key is empty")

    if bearer_token and api_key_token and bearer_token != api_key_token:
        raise AuthenticationError("Conflicting credentials were provided")
    if bearer_token:
        return bearer_token, "bearer"
    if api_key_token:
        return api_key_token, "api_key"
    raise AuthenticationError("Missing credentials")


def _resolve_user_code(static_tokens: dict[str, str], token: str, *, allow_default_dev_tokens: bool) -> str | None:
    configured_user_code = static_tokens.get(token)
    if configured_user_code:
        return configured_user_code
    if allow_default_dev_tokens and token.startswith(_DEV_TOKEN_PREFIX):
        return token.removeprefix(_DEV_TOKEN_PREFIX).strip() or None
    return None


def _record_auth_audit(
    request: Request,
    *,
    actor_user_id: int | None,
    action: str,
    comment: str,
) -> None:
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        return
    with session_factory() as session:
        session.add(
            AuditLog(
                entity_type="api_auth",
                entity_id=request.url.path,
                action=action,
                actor_user_id=actor_user_id,
                reason_code=None,
                comment=comment,
                before_json=None,
                after_json=None,
            )
        )
        session.commit()
