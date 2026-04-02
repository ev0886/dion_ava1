from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.application.composition import ApplicationContainer, create_bootstrapped_application_container
from app.config import AppSettings
from app.domain.enums import ItemStatus, StartupReadinessStatus, UserStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DION ABA1 operator CLI")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--sqlite-filename", type=str, default=None)
    parser.add_argument("--alembic-config-path", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("startup-check")
    subparsers.add_parser("hardware-health")
    subparsers.add_parser("recovery-scan")

    export_plan = subparsers.add_parser("export-plan")
    export_plan.add_argument("--requested-by-user-id", type=int, required=True)
    export_plan.add_argument("--destination-type", type=str, default="filesystem")
    export_plan.add_argument("--destination-path", type=str, default="var/exports")
    export_plan.add_argument("--comment", type=str, default=None)

    service_mode_open = subparsers.add_parser("service-mode-open")
    service_mode_open.add_argument("--user-id", type=int, required=True)
    service_mode_open.add_argument("--comment", type=str, default=None)

    service_mode_close = subparsers.add_parser("service-mode-close")
    service_mode_close.add_argument("--session-id", type=int, required=True)
    service_mode_close.add_argument("--user-id", type=int, required=True)
    service_mode_close.add_argument("--comment", type=str, default=None)

    create_user = subparsers.add_parser("create-user")
    create_user.add_argument("--user-code", type=str, required=True)
    create_user.add_argument("--full-name", type=str, required=True)
    create_user.add_argument("--role-id", type=int, required=True)
    create_user.add_argument("--actor-user-id", type=int, default=None)
    create_user.add_argument("--comment", type=str, default=None)

    update_user = subparsers.add_parser("update-user")
    update_user.add_argument("--user-id", type=int, required=True)
    update_user.add_argument("--user-code", type=str, default=None)
    update_user.add_argument("--full-name", type=str, default=None)
    update_user.add_argument("--role-id", type=int, default=None)
    update_user.add_argument("--actor-user-id", type=int, default=None)
    update_user.add_argument("--comment", type=str, default=None)
    update_user_state = update_user.add_mutually_exclusive_group()
    update_user_state.add_argument("--activate", action="store_true")
    update_user_state.add_argument("--deactivate", action="store_true")

    get_user = subparsers.add_parser("get-user")
    get_user.add_argument("--user-id", type=int, required=True)

    list_users = subparsers.add_parser("list-users")
    list_users.add_argument("--role-id", type=int, default=None)
    list_users.add_argument("--status", type=str, choices=[status.value for status in UserStatus], default=None)
    list_users.add_argument("--is-active", type=_parse_bool, default=None)
    list_users.add_argument("--search", type=str, default=None)

    create_item = subparsers.add_parser("create-item")
    create_item.add_argument("--sku", type=str, required=True)
    create_item.add_argument("--name", type=str, required=True)
    create_item.add_argument("--unit", type=str, required=True)
    create_item.add_argument("--item-group-id", type=int, default=None)
    create_item.add_argument("--description", type=str, default=None)
    create_item.add_argument("--return-allowed", action="store_true")
    create_item.add_argument("--min-level", type=int, default=0)
    create_item.add_argument("--actor-user-id", type=int, default=None)
    create_item.add_argument("--comment", type=str, default=None)

    update_item = subparsers.add_parser("update-item")
    update_item.add_argument("--item-id", type=int, required=True)
    update_item.add_argument("--sku", type=str, default=None)
    update_item.add_argument("--name", type=str, default=None)
    update_item.add_argument("--unit", type=str, default=None)
    update_item.add_argument("--item-group-id", type=int, default=None)
    update_item.add_argument("--description", type=str, default=None)
    update_item.add_argument("--return-allowed", type=_parse_bool, default=None)
    update_item.add_argument("--min-level", type=int, default=None)
    update_item.add_argument("--actor-user-id", type=int, default=None)
    update_item.add_argument("--comment", type=str, default=None)
    update_item_state = update_item.add_mutually_exclusive_group()
    update_item_state.add_argument("--activate", action="store_true")
    update_item_state.add_argument("--deactivate", action="store_true")

    get_item = subparsers.add_parser("get-item")
    get_item.add_argument("--item-id", type=int, required=True)

    list_items = subparsers.add_parser("list-items")
    list_items.add_argument("--item-group-id", type=int, default=None)
    list_items.add_argument("--status", type=str, choices=[status.value for status in ItemStatus], default=None)
    list_items.add_argument("--search", type=str, default=None)

    assign_permission = subparsers.add_parser("assign-permission")
    assign_permission.add_argument("--user-id", type=int, required=True)
    assign_permission.add_argument("--item-id", type=int, default=None)
    assign_permission.add_argument("--item-group-id", type=int, default=None)
    assign_permission.add_argument("--can-dispense", action="store_true")
    assign_permission.add_argument("--can-return", action="store_true")
    assign_permission.add_argument("--actor-user-id", type=int, default=None)
    assign_permission.add_argument("--comment", type=str, default=None)

    revoke_permission = subparsers.add_parser("revoke-permission")
    revoke_permission.add_argument("--permission-id", type=int, required=True)
    revoke_permission.add_argument("--actor-user-id", type=int, default=None)
    revoke_permission.add_argument("--comment", type=str, default=None)

    list_user_permissions = subparsers.add_parser("list-user-permissions")
    list_user_permissions.add_argument("--user-id", type=int, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = _settings_from_args(args)
    container = create_bootstrapped_application_container(settings)
    try:
        return _dispatch(args, container)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        container.close()


def _dispatch(args: argparse.Namespace, container: ApplicationContainer) -> int:
    if args.command == "startup-check":
        result = container.services.startup.run_startup_checks()
        print(_render(result))
        return 0 if result.readiness_status is not StartupReadinessStatus.NOT_READY else 1

    if args.command == "hardware-health":
        snapshot = container.hardware.facade.hardware_healthcheck()
        print(_render(snapshot))
        return 0 if snapshot.all_ok else 0

    if args.command == "recovery-scan":
        result = container.services.recovery.scan_recovery_targets()
        summary = {
            "unfinished_operation_ids": result.unfinished_operation_ids,
            "candidate_operation_ids": result.candidate_operation_ids,
            "open_case_count": result.open_case_count,
            "open_case_ids": tuple(
                case.recovery_case_id for case in result.open_cases if case.recovery_case_id is not None
            ),
        }
        print(_render(summary))
        return 0

    if args.command == "export-plan":
        snapshot = container.services.service_mode.get_hardware_snapshot(session_id=None)
        manifest = container.services.exports.build_diagnostic_dump_manifest(session_id=None, snapshot=snapshot)
        result = container.services.exports.prepare_export(
            requested_by_user_id=args.requested_by_user_id,
            destination_type=args.destination_type,
            destination_path=args.destination_path,
            diagnostic_manifest=manifest,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "service-mode-open":
        result = container.services.service_mode.enter_service_mode(
            user_id=args.user_id,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "service-mode-close":
        result = container.services.service_mode.exit_service_mode(
            session_id=args.session_id,
            user_id=args.user_id,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "create-user":
        result = container.services.users.create_user(
            user_code=args.user_code,
            full_name=args.full_name,
            role_id=args.role_id,
            actor_user_id=args.actor_user_id,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "update-user":
        if args.activate or args.deactivate:
            result = container.services.users.set_user_active(
                user_id=args.user_id,
                is_active=args.activate,
                actor_user_id=args.actor_user_id,
                comment=args.comment,
            )
        else:
            result = container.services.users.update_user(
                user_id=args.user_id,
                user_code=args.user_code,
                full_name=args.full_name,
                role_id=args.role_id,
                actor_user_id=args.actor_user_id,
                comment=args.comment,
            )
        print(_render(result))
        return 0

    if args.command == "get-user":
        print(_render(container.services.users.get_user_details(args.user_id)))
        return 0

    if args.command == "list-users":
        print(
            _render(
                container.services.users.list_users(
                    role_id=args.role_id,
                    status=UserStatus(args.status) if args.status else None,
                    is_active=args.is_active,
                    search=args.search,
                )
            )
        )
        return 0

    if args.command == "create-item":
        result = container.services.items.create_item(
            sku=args.sku,
            name=args.name,
            unit=args.unit,
            item_group_id=args.item_group_id,
            description=args.description,
            return_allowed=args.return_allowed,
            min_level=args.min_level,
            actor_user_id=args.actor_user_id,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "update-item":
        if args.activate or args.deactivate:
            result = container.services.items.set_item_active(
                item_id=args.item_id,
                is_active=args.activate,
                actor_user_id=args.actor_user_id,
                comment=args.comment,
            )
        else:
            result = container.services.items.update_item(
                item_id=args.item_id,
                sku=args.sku,
                name=args.name,
                unit=args.unit,
                item_group_id=args.item_group_id,
                description=args.description,
                return_allowed=args.return_allowed,
                min_level=args.min_level,
                actor_user_id=args.actor_user_id,
                comment=args.comment,
            )
        print(_render(result))
        return 0

    if args.command == "get-item":
        print(_render(container.services.items.get_item_details(args.item_id)))
        return 0

    if args.command == "list-items":
        print(
            _render(
                container.services.items.list_items(
                    item_group_id=args.item_group_id,
                    status=ItemStatus(args.status) if args.status else None,
                    search=args.search,
                )
            )
        )
        return 0

    if args.command == "assign-permission":
        result = container.services.permissions.assign_permission(
            user_id=args.user_id,
            item_id=args.item_id,
            item_group_id=args.item_group_id,
            can_dispense=args.can_dispense,
            can_return=args.can_return,
            actor_user_id=args.actor_user_id,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "revoke-permission":
        result = container.services.permissions.revoke_permission(
            permission_id=args.permission_id,
            actor_user_id=args.actor_user_id,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "list-user-permissions":
        print(_render(container.services.permissions.list_permissions_for_user(args.user_id)))
        return 0

    raise ValueError(f"Unsupported command: {args.command}")


def _settings_from_args(args: argparse.Namespace) -> AppSettings | None:
    if args.data_dir is None and args.sqlite_filename is None and args.alembic_config_path is None:
        return None
    return AppSettings(
        data_dir=args.data_dir or Path("var"),
        sqlite_filename=args.sqlite_filename or "dion_aba1.sqlite3",
        alembic_config_path=args.alembic_config_path or Path("alembic.ini"),
    )


def _render(value: Any) -> str:
    return json.dumps(_to_jsonable(value), indent=2, sort_keys=True)


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
