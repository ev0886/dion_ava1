from __future__ import annotations

import argparse
import sys

from app.application.composition import create_bootstrapped_application_container
from app.domain.enums import StartupReadinessStatus
from app.runtime import add_common_settings_arguments, render_json, settings_from_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.api", description="DION ABA1 API runtime")
    add_common_settings_arguments(parser, include_api=True)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--startup-check-only",
        action="store_true",
        help="Run existing startup/readiness checks and exit without starting the API server.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)

    if args.startup_check_only:
        return _run_startup_check(settings)

    return _run_server(args, settings)


def _run_startup_check(settings) -> int:
    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()
        print(render_json(result))
        return 0 if result.readiness_status is not StartupReadinessStatus.NOT_READY else 1
    finally:
        container.close()


def _run_server(args: argparse.Namespace, settings) -> int:
    try:
        import uvicorn
    except ImportError as error:
        print(f"ERROR: uvicorn is required to run the API server: {error}", file=sys.stderr)
        return 1

    from app.api.app import create_app

    app = create_app(settings)
    uvicorn.run(
        app,
        host=app.state.settings.api_host,
        port=app.state.settings.api_port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
