from __future__ import annotations

import argparse
import sys
from typing import Callable

from app.application.composition import ApplicationContainer, create_bootstrapped_application_container
from app.diagnostics import (
    run_rusguard_sdk_acm_probe_command,
    run_rusguard_sdk_acm_status_no_mask_command,
    run_rusguard_sdk_enumeration_command,
    run_rusguard_sdk_serial_open_diagnostic_command,
)
from app.domain.enums import StartupReadinessStatus
from app.runtime import add_common_settings_arguments, render_json, settings_from_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DION ABA1 operator CLI")
    add_common_settings_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("startup-check", help="Run startup readiness checks")
    subparsers.add_parser("hardware-health", help="Ping hardware endpoints and print availability")
    subparsers.add_parser("recovery-scan", help="Scan unfinished operations and open recovery cases")
    rusguard_enumerate = subparsers.add_parser(
        "rusguard-sdk-enumerate",
        help="Enumerate RusGuard SDK USB_HID and SERIAL endpoints",
    )
    rusguard_enumerate.add_argument("--library-path", type=str, default=None)
    rusguard_serial_diagnostic = subparsers.add_parser(
        "rusguard-sdk-serial-open-diagnostic",
        help="Probe discovered RusGuard SDK SERIAL endpoints with open/status/close",
    )
    rusguard_serial_diagnostic.add_argument("--library-path", type=str, default=None)
    rusguard_acm_probe = subparsers.add_parser(
        "rusguard-sdk-acm-probe",
        help="Probe only the discovered RusGuard SDK SERIAL endpoint at /dev/ttyACM0 using the vendor setup sequence",
    )
    rusguard_acm_probe.add_argument("--library-path", type=str, default=None)
    rusguard_acm_status_no_mask = subparsers.add_parser(
        "rusguard-sdk-acm-status-no-mask",
        help="Probe only the discovered RusGuard SDK SERIAL endpoint at /dev/ttyACM0 with init/status/close and no RG_SetCardsMask",
    )
    rusguard_acm_status_no_mask.add_argument("--library-path", type=str, default=None)

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
    diagnostic_runner = _diagnostic_runner(args.command)
    if diagnostic_runner is not None:
        return diagnostic_runner(library_path=args.library_path)
    settings = settings_from_args(args)
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
        print(render_json(result))
        return 0 if result.readiness_status is not StartupReadinessStatus.NOT_READY else 1

    if args.command == "hardware-health":
        snapshot = container.hardware.facade.hardware_healthcheck()
        print(render_json(snapshot))
        return 0 if snapshot.all_ok else 1

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
        print(render_json(summary))
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
        print(render_json(result))
        return 0

    if args.command == "service-mode-open":
        result = container.services.service_mode.enter_service_mode(
            user_id=args.user_id,
            comment=args.comment,
        )
        print(render_json(result))
        return 0

    if args.command == "service-mode-close":
        result = container.services.service_mode.exit_service_mode(
            session_id=args.session_id,
            user_id=args.user_id,
            comment=args.comment,
        )
        print(render_json(result))
        return 0

    raise ValueError(f"Unsupported command: {args.command}")


def _diagnostic_runner(command: str) -> Callable[..., int] | None:
    if command == "rusguard-sdk-enumerate":
        return run_rusguard_sdk_enumeration_command
    if command == "rusguard-sdk-serial-open-diagnostic":
        return run_rusguard_sdk_serial_open_diagnostic_command
    if command == "rusguard-sdk-acm-probe":
        return run_rusguard_sdk_acm_probe_command
    if command == "rusguard-sdk-acm-status-no-mask":
        return run_rusguard_sdk_acm_status_no_mask_command
    return None


if __name__ == "__main__":
    raise SystemExit(main())
