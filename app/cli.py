from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.application.composition import ApplicationContainer, create_bootstrapped_application_container
from app.config import AppSettings
from app.domain.enums import StartupReadinessStatus
from app.serialization import to_jsonable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DION ABA1 operator CLI")
    parser.add_argument("--data-dir", type=Path, default=None, help="Override the runtime data directory.")
    parser.add_argument("--sqlite-filename", type=str, default=None, help="Override the SQLite database filename.")
    parser.add_argument(
        "--alembic-config-path",
        type=Path,
        default=None,
        help="Override the Alembic config path used during bootstrap.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    subparsers.add_parser("startup-check", help="Run startup readiness checks.", description="Run startup readiness checks.")
    subparsers.add_parser(
        "hardware-health",
        help="Read the current hardware health snapshot.",
        description="Read the current hardware health snapshot.",
    )
    subparsers.add_parser(
        "recovery-scan",
        help="Scan for unfinished operations and recovery cases.",
        description="Scan for unfinished operations and recovery cases.",
    )

    export_plan = subparsers.add_parser(
        "export-plan",
        help="Prepare a diagnostics export plan.",
        description="Prepare a diagnostics export plan.",
    )
    export_plan.add_argument("--requested-by-user-id", type=int, required=True, help="User requesting the export.")
    export_plan.add_argument("--destination-type", type=str, default="filesystem", help="Export destination type.")
    export_plan.add_argument("--destination-path", type=str, default="var/exports", help="Export destination path.")
    export_plan.add_argument("--comment", type=str, default=None, help="Optional operator comment.")

    service_mode_open = subparsers.add_parser(
        "service-mode-open",
        help="Open a service-mode session.",
        description="Open a service-mode session.",
    )
    service_mode_open.add_argument("--user-id", type=int, required=True, help="Operator or admin user id.")
    service_mode_open.add_argument("--comment", type=str, default=None, help="Optional operator comment.")

    service_mode_close = subparsers.add_parser(
        "service-mode-close",
        help="Close a service-mode session.",
        description="Close a service-mode session.",
    )
    service_mode_close.add_argument("--session-id", type=int, required=True, help="Service-mode session id.")
    service_mode_close.add_argument("--user-id", type=int, required=True, help="Operator or admin user id.")
    service_mode_close.add_argument("--comment", type=str, default=None, help="Optional operator comment.")

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

    raise ValueError(f"Unsupported command: {args.command}")


def _settings_from_args(args: argparse.Namespace) -> AppSettings | None:
    if args.data_dir is None and args.sqlite_filename is None and args.alembic_config_path is None:
        return None
    return AppSettings(
        data_dir=args.data_dir or Path("var"),
        sqlite_filename=args.sqlite_filename or "dion_aba1.sqlite3",
        alembic_config_path=args.alembic_config_path or Path("alembic.ini"),
    )


def _render(value: object) -> str:
    return json.dumps(to_jsonable(value), indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
