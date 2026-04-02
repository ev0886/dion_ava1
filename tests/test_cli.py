from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.domain.enums import StartupReadinessStatus
from app.hardware.dto import HardwareOperationStatus


def test_startup_check_returns_success_for_healthy_temp_environment(tmp_path: Path) -> None:
    exit_code, stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_healthy.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "startup-check",
        ]
    )

    assert exit_code == 0
    assert '"readiness_status": "ready"' in stdout
    assert "ERROR:" not in stderr


def test_startup_check_returns_non_zero_when_startup_is_not_ready(monkeypatch) -> None:
    def _fake_container(_settings):
        return _FakeContainer(
            startup_result=StartupReadinessDTO(
                database=DatabaseReadinessDTO(
                    ok=False,
                    simple_query_ok=False,
                    alembic_version_table_present=False,
                    message="db failed",
                ),
                hardware=HardwareReadinessDTO(ok=False, degraded=False, entries=(), message=None),
                recovery=RecoveryReadinessDTO(
                    ok=False,
                    recovery_candidates_found=False,
                    recovery_candidate_count=0,
                    recovery_case_count=0,
                    candidate_operation_ids=(),
                    message=None,
                ),
                readiness_status=StartupReadinessStatus.NOT_READY,
                message="db failed",
            )
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(["startup-check"])

    assert exit_code == 1
    assert '"readiness_status": "not_ready"' in stdout
    assert stderr == ""


def test_hardware_health_prints_three_mock_device_statuses(tmp_path: Path) -> None:
    exit_code, stdout, _stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_hardware.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "hardware-health",
        ]
    )

    assert exit_code == 0
    assert '"drum"' in stdout
    assert '"lock"' in stdout
    assert '"rfid"' in stdout


def test_recovery_scan_runs_and_prints_deterministic_summary(tmp_path: Path) -> None:
    exit_code, stdout, _stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_recovery.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "recovery-scan",
        ]
    )

    assert exit_code == 0
    assert '"candidate_operation_ids": []' in stdout
    assert '"open_case_count": 0' in stdout
    assert '"unfinished_operation_ids": []' in stdout


def test_management_cli_commands_cover_minimal_workflow(monkeypatch) -> None:
    fake_container = _FakeManagementContainer()
    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", lambda _settings: fake_container)

    create_user = _run_cli(["create-user", "--user-code", "cli-user-2", "--full-name", "CLI User Two", "--role-id", "1"])
    update_user = _run_cli(["update-user", "--user-id", "2", "--deactivate"])
    get_user = _run_cli(["get-user", "--user-id", "2"])
    list_users = _run_cli(["list-users"])
    create_item = _run_cli(["create-item", "--sku", "cli-item-2", "--name", "CLI Item Two", "--unit", "pcs", "--item-group-id", "1"])
    update_item = _run_cli(["update-item", "--item-id", "2", "--deactivate"])
    get_item = _run_cli(["get-item", "--item-id", "2"])
    list_items = _run_cli(["list-items"])
    assign_permission = _run_cli(["assign-permission", "--user-id", "2", "--item-id", "2", "--can-dispense"])
    list_permissions = _run_cli(["list-user-permissions", "--user-id", "2"])
    revoke_permission = _run_cli(["revoke-permission", "--permission-id", "1"])

    assert create_user[0] == 0
    assert '"user_code": "cli-user-2"' in create_user[1]
    assert update_user[0] == 0
    assert '"status": "inactive"' in update_user[1]
    assert get_user[0] == 0
    assert '"user_id": 2' in get_user[1]
    assert list_users[0] == 0
    assert '"users"' in list_users[1]
    assert create_item[0] == 0
    assert '"sku": "cli-item-2"' in create_item[1]
    assert update_item[0] == 0
    assert '"status": "inactive"' in update_item[1]
    assert get_item[0] == 0
    assert '"item_id": 2' in get_item[1]
    assert list_items[0] == 0
    assert '"items"' in list_items[1]
    assert assign_permission[0] == 0
    assert '"permission_id": 1' in assign_permission[1]
    assert list_permissions[0] == 0
    assert '"permissions"' in list_permissions[1]
    assert revoke_permission[0] == 0
    assert '"is_active": false' in revoke_permission[1]


@dataclass(slots=True)
class _FakeStartupService:
    result: StartupReadinessDTO

    def run_startup_checks(self) -> StartupReadinessDTO:
        return self.result


@dataclass(slots=True)
class _FakeContainer:
    startup_result: StartupReadinessDTO
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(startup=_FakeStartupService(self.startup_result))

    def close(self) -> None:
        return None


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()

class _FakeManagementService:
    def __init__(self) -> None:
        self.users = {
            1: {"user_id": 1, "user_code": "cli-admin", "full_name": "CLI Admin", "status": "active", "is_active": True},
        }
        self.items = {
            1: {"item_id": 1, "sku": "cli-item-1", "name": "CLI Item One", "status": "active"},
        }
        self.permissions: dict[int, dict[str, object]] = {}

    def create_user(self, **kwargs):
        user = {
            "user_id": 2,
            "user_code": kwargs["user_code"],
            "full_name": kwargs["full_name"],
            "status": "active",
            "is_active": True,
        }
        self.users[2] = user
        return user

    def update_user(self, **kwargs):
        user = self.users[kwargs["user_id"]]
        if kwargs.get("user_code") is not None:
            user["user_code"] = kwargs["user_code"]
        if kwargs.get("full_name") is not None:
            user["full_name"] = kwargs["full_name"]
        return user

    def set_user_active(self, **kwargs):
        user = self.users[kwargs["user_id"]]
        user["is_active"] = kwargs["is_active"]
        user["status"] = "active" if kwargs["is_active"] else "inactive"
        return user

    def get_user_details(self, user_id: int):
        return self.users[user_id]

    def list_users(self, **_kwargs):
        return {"users": list(self.users.values())}

    def create_item(self, **kwargs):
        item = {"item_id": 2, "sku": kwargs["sku"], "name": kwargs["name"], "status": "active"}
        self.items[2] = item
        return item

    def update_item(self, **kwargs):
        item = self.items[kwargs["item_id"]]
        if kwargs.get("sku") is not None:
            item["sku"] = kwargs["sku"]
        if kwargs.get("name") is not None:
            item["name"] = kwargs["name"]
        return item

    def set_item_active(self, **kwargs):
        item = self.items[kwargs["item_id"]]
        item["status"] = "active" if kwargs["is_active"] else "inactive"
        return item

    def get_item_details(self, item_id: int):
        return self.items[item_id]

    def list_items(self, **_kwargs):
        return {"items": list(self.items.values())}

    def assign_permission(self, **kwargs):
        permission = {
            "permission_id": 1,
            "user_id": kwargs["user_id"],
            "item_id": kwargs.get("item_id"),
            "item_group_id": kwargs.get("item_group_id"),
            "is_active": True,
        }
        self.permissions[1] = permission
        return permission

    def revoke_permission(self, **kwargs):
        permission = self.permissions[kwargs["permission_id"]]
        permission["is_active"] = False
        return permission

    def list_permissions_for_user(self, user_id: int):
        return {"user_id": user_id, "permissions": list(self.permissions.values())}


class _FakeManagementContainer:
    def __init__(self) -> None:
        management = _FakeManagementService()
        self.services = SimpleNamespace(
            users=management,
            items=management,
            permissions=management,
        )

    def close(self) -> None:
        return None
