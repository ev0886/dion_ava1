from __future__ import annotations

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api import create_app
from app.application.dto.imports import ImportExecutionRequestDTO
from app.application.import_service import ImportExecutionService
from app.cli import main
from app.config import AppSettings
from app.domain.enums import ItemStatus, RoleCode, UserStatus
from app.persistence.base import Base
from app.persistence.models import AuditLog, Item, Role, User
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository
from app.persistence.repositories.users import UserRepository


def test_user_import_dry_run_happy_path(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "user_import_dry_run.sqlite3")
    source_path = _write_json(
        tmp_path / "users.json",
        [
            {"user_code": "user-existing", "full_name": "Updated Name", "role_code": "operator", "status": "active"},
            {"user_code": "user-new", "full_name": "New User", "role_code": "user", "status": "inactive"},
        ],
    )

    with factory() as session:
        _seed_roles_and_records(session)
        service = _service(session)

        result = service.execute_user_import(
            ImportExecutionRequestDTO(
                target_type="users",
                mode="dry_run",
                source_path=str(source_path),
                requested_by_user_id=1,
            )
        )

        assert result.summary.total_rows == 2
        assert result.summary.created_count == 1
        assert result.summary.updated_count == 1
        assert result.summary.invalid_rows == 0
        assert result.applied_changes.created_count == 0
        assert session.execute(select(User).where(User.user_code == "user-new")).scalar_one_or_none() is None
        existing = session.execute(select(User).where(User.user_code == "user-existing")).scalar_one()
        assert existing.full_name == "Existing User"
        assert session.execute(select(AuditLog)).scalars().all() == []


def test_user_import_apply_happy_path_creates_updates_and_audits(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "user_import_apply.sqlite3")
    source_path = _write_json(
        tmp_path / "users_apply.json",
        [
            {"user_code": "user-existing", "full_name": "Updated Name", "role_code": "operator", "status": "blocked"},
            {"user_code": "user-new", "full_name": "New User", "role_code": "user", "status": "active"},
        ],
    )

    with factory() as session:
        ids = _seed_roles_and_records(session)
        service = _service(session)

        result = service.execute_user_import(
            ImportExecutionRequestDTO(
                target_type="users",
                mode="apply",
                source_path=str(source_path),
                requested_by_user_id=ids["admin_user_id"],
            )
        )

        assert result.summary.created_count == 1
        assert result.summary.updated_count == 1
        assert result.applied_changes.created_count == 1
        assert result.applied_changes.updated_count == 1

        created = session.execute(select(User).where(User.user_code == "user-new")).scalar_one()
        updated = session.execute(select(User).where(User.user_code == "user-existing")).scalar_one()
        audit_logs = session.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()

        assert created.full_name == "New User"
        assert updated.full_name == "Updated Name"
        assert updated.status is UserStatus.BLOCKED
        assert len(audit_logs) == 2
        assert audit_logs[0].action == "import_update"
        assert audit_logs[1].action == "import_create"


def test_user_import_invalid_row_rejection(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "user_import_invalid.sqlite3")
    source_path = _write_json(
        tmp_path / "users_invalid.json",
        [{"user_code": "bad-user", "full_name": "", "role_code": "missing-role"}],
    )

    with factory() as session:
        _seed_roles_and_records(session)
        service = _service(session)

        result = service.execute_user_import(
            ImportExecutionRequestDTO(target_type="users", mode="dry_run", source_path=str(source_path))
        )

        assert result.summary.invalid_rows == 1
        assert result.summary.error_count == 1
        assert result.rows[0].action == "error"
        assert {message.code for message in result.rows[0].messages} == {"missing_full_name", "invalid_role_code"}


def test_item_import_dry_run_happy_path(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "item_import_dry_run.sqlite3")
    source_path = _write_csv(
        tmp_path / "items.csv",
        "sku,name,unit,description,return_allowed,min_level,status\n"
        "item-existing,Updated Item,box,Updated description,true,3,inactive\n"
        "item-new,New Item,pcs,,false,1,active\n",
    )

    with factory() as session:
        _seed_roles_and_records(session)
        service = _service(session)

        result = service.execute_item_import(
            ImportExecutionRequestDTO(target_type="items", mode="dry_run", source_path=str(source_path))
        )

        assert result.summary.created_count == 1
        assert result.summary.updated_count == 1
        assert result.applied_changes.updated_count == 0
        assert session.execute(select(Item).where(Item.sku == "item-new")).scalar_one_or_none() is None
        existing = session.execute(select(Item).where(Item.sku == "item-existing")).scalar_one()
        assert existing.name == "Existing Item"


def test_item_import_apply_happy_path_creates_updates_and_audits(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "item_import_apply.sqlite3")
    source_path = _write_csv(
        tmp_path / "items_apply.csv",
        "sku,name,unit,description,return_allowed,min_level,status\n"
        "item-existing,Updated Item,box,Updated description,true,3,inactive\n"
        "item-new,New Item,pcs,,false,1,active\n",
    )

    with factory() as session:
        ids = _seed_roles_and_records(session)
        service = _service(session)

        result = service.execute_item_import(
            ImportExecutionRequestDTO(
                target_type="items",
                mode="apply",
                source_path=str(source_path),
                requested_by_user_id=ids["admin_user_id"],
            )
        )

        assert result.summary.created_count == 1
        assert result.summary.updated_count == 1
        updated = session.execute(select(Item).where(Item.sku == "item-existing")).scalar_one()
        created = session.execute(select(Item).where(Item.sku == "item-new")).scalar_one()
        audit_logs = session.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()

        assert updated.name == "Updated Item"
        assert updated.status is ItemStatus.INACTIVE
        assert created.min_level == 1
        assert len(audit_logs) == 2
        assert {entry.entity_type for entry in audit_logs} == {"item"}


def test_item_import_invalid_row_rejection(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "item_import_invalid.sqlite3")
    source_path = _write_csv(
        tmp_path / "items_invalid.csv",
        "sku,name,unit,min_level\nitem-bad,Bad Item,pcs,-1\n",
    )

    with factory() as session:
        _seed_roles_and_records(session)
        service = _service(session)

        result = service.execute_item_import(
            ImportExecutionRequestDTO(target_type="items", mode="dry_run", source_path=str(source_path))
        )

        assert result.summary.invalid_rows == 1
        assert result.rows[0].action == "error"
        assert result.rows[0].messages[0].code == "invalid_min_level"


def test_import_rejects_unsupported_format(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "import_invalid_format.sqlite3")
    source_path = tmp_path / "users.txt"
    source_path.write_text("unsupported", encoding="utf-8")

    with factory() as session:
        _seed_roles_and_records(session)
        service = _service(session)

        try:
            service.execute(
                ImportExecutionRequestDTO(target_type="users", mode="dry_run", source_path=str(source_path))
            )
        except Exception as error:
            assert str(error) == "Unsupported import format: .txt"
        else:
            raise AssertionError("Expected unsupported format validation error")


def test_import_rejects_missing_file(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path, "import_missing_file.sqlite3")

    with factory() as session:
        _seed_roles_and_records(session)
        service = _service(session)

        try:
            service.execute(
                ImportExecutionRequestDTO(
                    target_type="items",
                    mode="dry_run",
                    source_path=str(tmp_path / "missing.csv"),
                )
            )
        except Exception as error:
            assert str(error).startswith("Import source file not found:")
        else:
            raise AssertionError("Expected missing file error")


def test_import_api_endpoints(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "import_api.sqlite3"))
    source_path = _write_json(
        tmp_path / "users_api.json",
        [{"user_code": "user-api", "full_name": "API User", "role_code": "user"}],
    )
    _seed_app(app)

    with TestClient(app) as client:
        formats_response = client.get("/imports/formats")
        execute_response = client.post(
            "/imports/execute",
            json={"target_type": "users", "mode": "dry_run", "source_path": str(source_path)},
        )

    assert formats_response.status_code == 200
    assert formats_response.json()["formats"] == ["json", "csv"]
    assert execute_response.status_code == 200
    assert execute_response.json()["summary"]["target_type"] == "users"
    assert execute_response.json()["rows"][0]["action"] == "create"


def test_import_cli_commands(tmp_path: Path) -> None:
    source_path = _write_json(
        tmp_path / "users_cli.json",
        [{"user_code": "user-cli", "full_name": "CLI User", "role_code": "user"}],
    )
    _seed_cli_database(tmp_path, "import_cli.sqlite3")

    list_exit_code, list_stdout, list_stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "import_cli.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "list-import-formats",
        ]
    )
    execute_exit_code, execute_stdout, execute_stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "import_cli.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "execute-import",
            "--target-type",
            "users",
            "--mode",
            "dry_run",
            "--source-path",
            str(source_path),
        ]
    )

    assert list_exit_code == 0
    assert '"formats": [' in list_stdout
    assert "ERROR:" not in list_stderr
    assert execute_exit_code == 0
    assert '"target_type": "users"' in execute_stdout
    assert "ERROR:" not in execute_stderr


def _service(session: Session) -> ImportExecutionService:
    return ImportExecutionService(
        user_repository=UserRepository(session),
        inventory_repository=InventoryRepository(session),
        audit_log_repository=AuditLogRepository(session),
    )


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _session_factory(tmp_path: Path, sqlite_filename: str) -> sessionmaker[Session]:
    settings = _settings(tmp_path, sqlite_filename)
    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_roles_and_records(session: Session) -> dict[str, int]:
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    user_role = Role(code=RoleCode.USER, name="User")
    session.add_all((admin_role, operator_role, user_role))
    session.flush()
    admin = User(
        role_id=admin_role.id,
        user_code="admin-1",
        full_name="Admin User",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    existing_user = User(
        role_id=user_role.id,
        user_code="user-existing",
        full_name="Existing User",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    existing_item = Item(
        item_group_id=None,
        sku="item-existing",
        name="Existing Item",
        description="Existing description",
        unit="pcs",
        return_allowed=False,
        min_level=0,
        status=ItemStatus.ACTIVE,
    )
    session.add_all((admin, existing_user, existing_item))
    session.commit()
    return {"admin_user_id": admin.id}


def _seed_app(app) -> None:
    with app.state.session_factory() as session:
        _seed_roles_and_records(session)


def _seed_cli_database(tmp_path: Path, sqlite_filename: str) -> None:
    app = create_app(_settings(tmp_path, sqlite_filename))
    with app.state.session_factory() as session:
        _seed_roles_and_records(session)


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_csv(path: Path, contents: str) -> Path:
    path.write_text(contents, encoding="utf-8")
    return path


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
