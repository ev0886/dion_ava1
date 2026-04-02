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
from app.application.dto.logs import AuditLogQueryFilters, EventLogQueryFilters
from app.application.dto.operations import OperationQueryFilters
from app.application.dto.recovery import RecoveryCaseQueryFilters
from app.domain.enums import (
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    StartupReadinessStatus,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DION ABA1 operator CLI")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--sqlite-filename", type=str, default=None)
    parser.add_argument("--alembic-config-path", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("startup-check")
    subparsers.add_parser("hardware-health")
    subparsers.add_parser("recovery-scan")

    list_operations = subparsers.add_parser("list-operations")
    list_operations.add_argument("--operation-type", type=str, default=None)
    list_operations.add_argument("--operation-state", type=str, default=None)
    list_operations.add_argument("--user-id", type=int, default=None)
    list_operations.add_argument("--item-id", type=int, default=None)
    list_operations.add_argument("--slot-id", type=int, default=None)
    list_operations.add_argument("--session-id", type=int, default=None)
    list_operations.add_argument("--limit", type=int, default=100)

    get_operation = subparsers.add_parser("get-operation")
    get_operation.add_argument("--operation-id", type=int, required=True)

    get_operation_history = subparsers.add_parser("get-operation-history")
    get_operation_history.add_argument("--operation-id", type=int, required=True)

    list_recovery_cases = subparsers.add_parser("list-recovery-cases")
    list_recovery_cases.add_argument("--status", type=str, default=None)
    list_recovery_cases.add_argument("--classification", type=str, default=None)
    list_recovery_cases.add_argument("--limit", type=int, default=100)

    get_recovery_case = subparsers.add_parser("get-recovery-case")
    get_recovery_case.add_argument("--recovery-case-id", type=int, required=True)

    list_audit_logs = subparsers.add_parser("list-audit-logs")
    list_audit_logs.add_argument("--entity-type", type=str, default=None)
    list_audit_logs.add_argument("--actor-user-id", type=int, default=None)
    list_audit_logs.add_argument("--limit", type=int, default=100)

    list_event_logs = subparsers.add_parser("list-event-logs")
    list_event_logs.add_argument("--event-type", type=str, default=None)
    list_event_logs.add_argument("--level", type=str, default=None)
    list_event_logs.add_argument("--limit", type=int, default=100)

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

    if args.command == "list-operations":
        result = container.services.operations_query.list_operations(
            OperationQueryFilters(
                operation_type=OperationType(args.operation_type) if args.operation_type else None,
                operation_state=OperationState(args.operation_state) if args.operation_state else None,
                user_id=args.user_id,
                item_id=args.item_id,
                slot_id=args.slot_id,
                session_id=args.session_id,
                limit=args.limit,
            )
        )
        print(_render(result))
        return 0

    if args.command == "get-operation":
        result = container.services.operations_query.get_operation(args.operation_id)
        print(_render(result))
        return 0

    if args.command == "get-operation-history":
        result = container.services.operations_query.get_operation_history(args.operation_id)
        print(_render(result))
        return 0

    if args.command == "list-recovery-cases":
        result = container.services.recovery.list_cases(
            RecoveryCaseQueryFilters(
                status=RecoveryStatus(args.status) if args.status else None,
                classification=RecoveryClassification(args.classification) if args.classification else None,
                limit=args.limit,
            )
        )
        print(_render(result))
        return 0

    if args.command == "get-recovery-case":
        result = container.services.recovery.get_case_detail(args.recovery_case_id)
        print(_render(result))
        return 0

    if args.command == "list-audit-logs":
        result = container.services.logs_query.list_audit_logs(
            AuditLogQueryFilters(
                entity_type=args.entity_type,
                actor_user_id=args.actor_user_id,
                limit=args.limit,
            )
        )
        print(_render(result))
        return 0

    if args.command == "list-event-logs":
        result = container.services.logs_query.list_event_logs(
            EventLogQueryFilters(
                event_type=args.event_type,
                level=args.level,
                limit=args.limit,
            )
        )
        print(_render(result))
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
