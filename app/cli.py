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
from app.domain.enums import StartupReadinessStatus


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

    create_slot = subparsers.add_parser("create-slot")
    create_slot.add_argument("--code", type=str, required=True)
    create_slot.add_argument("--slot-type", type=str, required=True)
    create_slot.add_argument("--drum-position", type=int, required=True)
    create_slot.add_argument("--board-address", type=int, required=True)
    create_slot.add_argument("--lock-number", type=int, required=True)
    create_slot.add_argument("--capacity", type=int, default=None)
    create_slot.add_argument("--status", type=str, default="active")
    create_slot.add_argument("--actor-user-id", type=int, default=None)
    create_slot.add_argument("--reason-code", type=str, default=None)
    create_slot.add_argument("--comment", type=str, default=None)

    update_slot = subparsers.add_parser("update-slot")
    update_slot.add_argument("--slot-id", type=int, required=True)
    update_slot.add_argument("--code", type=str, default=None)
    update_slot.add_argument("--slot-type", type=str, default=None)
    update_slot.add_argument("--drum-position", type=int, default=None)
    update_slot.add_argument("--board-address", type=int, default=None)
    update_slot.add_argument("--lock-number", type=int, default=None)
    update_slot.add_argument("--capacity", type=int, default=None)
    update_slot.add_argument("--status", type=str, default=None)
    update_slot.add_argument("--activate", action="store_true")
    update_slot.add_argument("--deactivate", action="store_true")
    update_slot.add_argument("--actor-user-id", type=int, default=None)
    update_slot.add_argument("--reason-code", type=str, default=None)
    update_slot.add_argument("--comment", type=str, default=None)

    get_slot = subparsers.add_parser("get-slot")
    get_slot.add_argument("--slot-id", type=int, required=True)

    list_slots = subparsers.add_parser("list-slots")

    create_slot_binding = subparsers.add_parser("create-slot-binding")
    create_slot_binding.add_argument("--slot-id", type=int, required=True)
    create_slot_binding.add_argument("--item-id", type=int, required=True)
    create_slot_binding.add_argument("--binding-type", type=str, required=True)
    create_slot_binding.add_argument("--actor-user-id", type=int, default=None)
    create_slot_binding.add_argument("--reason-code", type=str, default=None)
    create_slot_binding.add_argument("--comment", type=str, default=None)

    deactivate_slot_binding = subparsers.add_parser("deactivate-slot-binding")
    deactivate_slot_binding.add_argument("--binding-id", type=int, required=True)
    deactivate_slot_binding.add_argument("--actor-user-id", type=int, default=None)
    deactivate_slot_binding.add_argument("--reason-code", type=str, default=None)
    deactivate_slot_binding.add_argument("--comment", type=str, default=None)

    list_slot_bindings = subparsers.add_parser("list-slot-bindings")
    list_slot_bindings.add_argument("--slot-id", type=int, required=True)

    list_item_bindings = subparsers.add_parser("list-item-bindings")
    list_item_bindings.add_argument("--item-id", type=int, required=True)

    list_inventory_balances = subparsers.add_parser("list-inventory-balances")
    list_inventory_balances.add_argument("--slot-id", type=int, default=None)
    list_inventory_balances.add_argument("--item-id", type=int, default=None)

    adjust_inventory = subparsers.add_parser("adjust-inventory")
    adjust_inventory.add_argument("--slot-id", type=int, required=True)
    adjust_inventory.add_argument("--item-id", type=int, required=True)
    adjust_inventory.add_argument("--quantity-delta", type=int, required=True)
    adjust_inventory.add_argument("--actor-user-id", type=int, default=None)
    adjust_inventory.add_argument("--reason-code", type=str, default=None)
    adjust_inventory.add_argument("--comment", type=str, default=None)

    set_inventory = subparsers.add_parser("set-inventory")
    set_inventory.add_argument("--slot-id", type=int, required=True)
    set_inventory.add_argument("--item-id", type=int, required=True)
    set_inventory.add_argument("--quantity", type=int, required=True)
    set_inventory.add_argument("--actor-user-id", type=int, default=None)
    set_inventory.add_argument("--reason-code", type=str, default=None)
    set_inventory.add_argument("--comment", type=str, default=None)

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

    if args.command == "create-slot":
        result = container.services.slots.create_slot(
            code=args.code,
            slot_type=args.slot_type,
            drum_position=args.drum_position,
            board_address=args.board_address,
            lock_number=args.lock_number,
            capacity=args.capacity,
            status=args.status,
            actor_user_id=args.actor_user_id,
            reason_code=args.reason_code,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "update-slot":
        if args.activate and args.deactivate:
            raise ValueError("Only one of --activate or --deactivate may be specified")
        if args.activate:
            result = container.services.slots.activate_slot(
                slot_id=args.slot_id,
                actor_user_id=args.actor_user_id,
                reason_code=args.reason_code,
                comment=args.comment,
            )
        elif args.deactivate:
            result = container.services.slots.deactivate_slot(
                slot_id=args.slot_id,
                actor_user_id=args.actor_user_id,
                reason_code=args.reason_code,
                comment=args.comment,
            )
        else:
            result = container.services.slots.update_slot(
                slot_id=args.slot_id,
                code=args.code,
                slot_type=args.slot_type,
                drum_position=args.drum_position,
                board_address=args.board_address,
                lock_number=args.lock_number,
                capacity=args.capacity,
                status=args.status,
                actor_user_id=args.actor_user_id,
                reason_code=args.reason_code,
                comment=args.comment,
            )
        print(_render(result))
        return 0

    if args.command == "get-slot":
        print(_render(container.services.slots.get_slot_details(args.slot_id)))
        return 0

    if args.command == "list-slots":
        print(_render(container.services.slots.list_slots()))
        return 0

    if args.command == "create-slot-binding":
        result = container.services.slots.create_binding(
            slot_id=args.slot_id,
            item_id=args.item_id,
            binding_type=args.binding_type,
            actor_user_id=args.actor_user_id,
            reason_code=args.reason_code,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "deactivate-slot-binding":
        result = container.services.slots.deactivate_binding(
            binding_id=args.binding_id,
            actor_user_id=args.actor_user_id,
            reason_code=args.reason_code,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "list-slot-bindings":
        print(_render(container.services.slots.list_bindings_for_slot(args.slot_id)))
        return 0

    if args.command == "list-item-bindings":
        print(_render(container.services.slots.list_bindings_for_item(args.item_id)))
        return 0

    if args.command == "list-inventory-balances":
        print(_render(container.services.inventory.list_balances(slot_id=args.slot_id, item_id=args.item_id)))
        return 0

    if args.command == "adjust-inventory":
        result = container.services.inventory_admin.adjust_inventory(
            slot_id=args.slot_id,
            item_id=args.item_id,
            quantity_delta=args.quantity_delta,
            actor_user_id=args.actor_user_id,
            reason_code=args.reason_code,
            comment=args.comment,
        )
        print(_render(result))
        return 0

    if args.command == "set-inventory":
        result = container.services.inventory_admin.set_inventory(
            slot_id=args.slot_id,
            item_id=args.item_id,
            quantity=args.quantity,
            actor_user_id=args.actor_user_id,
            reason_code=args.reason_code,
            comment=args.comment,
        )
        print(_render(result))
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


def _to_jsonable(value: Any) -> Any:
    from datetime import date, datetime

    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
