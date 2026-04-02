from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.application.composition import ApplicationContainer, build_application_container
from app.config import AppSettings


def get_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_application_container(
    request: Request,
    session: Session = Depends(get_db_session),
) -> ApplicationContainer:
    return build_application_container(
        settings=request.app.state.settings,
        engine=request.app.state.engine,
        session_factory=request.app.state.session_factory,
        session=session,
    )
