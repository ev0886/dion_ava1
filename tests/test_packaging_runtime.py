from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.api.__main__ import main as api_main
from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.config import AppSettings, HardwareProvider
from app.domain.enums import StartupReadinessStatus


def test_env_example_loads_into_settings() -> None:
    settings = AppSettings(_env_file=Path(".env.example"), _env_file_encoding="utf-8")

    assert settings.app_environment == "development"
    assert settings.hardware_provider is HardwareProvider.MOCK
    assert settings.hardware_real_endpoints == {}
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000


def test_api_startup_check_only_uses_existing_startup_service(monkeypatch) -> None:
    startup_result = StartupReadinessDTO(
        database=DatabaseReadinessDTO(
            ok=True,
            simple_query_ok=True,
            alembic_version_table_present=True,
            message=None,
        ),
        hardware=HardwareReadinessDTO(ok=True, degraded=False, entries=(), message=None),
        recovery=RecoveryReadinessDTO(
            ok=True,
            recovery_candidates_found=False,
            recovery_candidate_count=0,
            recovery_case_count=0,
            candidate_operation_ids=(),
            message=None,
        ),
        readiness_status=StartupReadinessStatus.READY,
        message="Startup checks passed.",
    )

    monkeypatch.setattr("app.api.__main__.create_bootstrapped_application_container", lambda _settings: _FakeContainer(startup_result))

    exit_code, stdout, stderr = _run_api_main(["--startup-check-only"])

    assert exit_code == 0
    assert '"readiness_status": "ready"' in stdout
    assert stderr == ""


def test_api_runner_invokes_uvicorn_with_resolved_settings(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    fake_uvicorn = ModuleType("uvicorn")

    def _fake_run(app, *, host, port, reload):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port
        captured["reload"] = reload

    fake_uvicorn.run = _fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    exit_code, stdout, stderr = _run_api_main(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "runner.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "--host",
            "0.0.0.0",
            "--port",
            "9010",
        ]
    )

    assert exit_code == 0
    assert stdout == ""
    assert "initial schema" in stderr
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9010
    assert captured["reload"] is False


def test_pyproject_declares_runtime_entry_points() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["dion-bootstrap"] == "app.main:main"
    assert pyproject["project"]["scripts"]["dion-cli"] == "app.cli:main"
    assert pyproject["project"]["scripts"]["dion-api"] == "app.api.__main__:main"


def test_raspberry_pi_kiosk_assets_target_local_ui_mvp() -> None:
    deploy_dir = Path("deploy/raspberry-pi")

    launcher = (deploy_dir / "launch_ui_mvp_kiosk.sh").read_text(encoding="utf-8")
    desktop_entry = (deploy_dir / "dion-ui-mvp-kiosk.desktop").read_text(encoding="utf-8")
    api_service = (deploy_dir / "dion-api.service").read_text(encoding="utf-8")
    kiosk_doc = Path("docs/raspberry-pi-kiosk.md").read_text(encoding="utf-8")

    assert 'http://127.0.0.1:8000/ui/mvp' in launcher
    assert 'http://127.0.0.1:8000/health' in launcher
    assert "--kiosk" in launcher
    assert "Exec=/opt/dion_ava1/deploy/raspberry-pi/launch_ui_mvp_kiosk.sh" in desktop_entry
    assert "DION_PYTHON_BIN" in api_service
    assert "-m app.api" in api_service
    assert "dion-api.service" in kiosk_doc


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


def _run_api_main(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = api_main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
