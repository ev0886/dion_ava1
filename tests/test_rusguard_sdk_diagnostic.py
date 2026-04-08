from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from app import cli as cli_module
from app.cli import main
from app.diagnostics.rusguard_sdk import (
    DiagnosticReport,
    DiagnosticSection,
    render_report,
    run_rusguard_sdk_enumeration_command,
    run_safe_diagnostic,
)


def test_render_report_shows_safe_skip_sections() -> None:
    report = render_report(
        DiagnosticReport(
            library_path=Path("/opt/rusguard/librgsec.so"),
            sections=(
                DiagnosticSection(
                    title="USB_HID",
                    lines=("find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo",),
                ),
                DiagnosticSection(
                    title="SERIAL",
                    lines=("find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo",),
                ),
            ),
        )
    )

    assert report == (
        "[RusGuard SDK]\n"
        "library path: /opt/rusguard/librgsec.so\n"
        "library load ok\n"
        "initialize ok\n"
        "\n"
        "[USB_HID]\n"
        "find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo\n"
        "\n"
        "[SERIAL]\n"
        "find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo\n"
        "\n"
        "uninitialize ok"
    )


def test_run_safe_diagnostic_initializes_and_uninitializes_without_endpoint_discovery() -> None:
    sdk = _FakeSdk()

    report = run_safe_diagnostic(sdk)

    assert sdk.calls == ["initialize", "uninitialize"]
    assert report == DiagnosticReport(
        library_path=Path("/fake/librgsec.so"),
        sections=(
            DiagnosticSection(
                title="USB_HID",
                lines=("find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo",),
            ),
            DiagnosticSection(
                title="SERIAL",
                lines=("find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo",),
            ),
        ),
    )


def test_cli_rusguard_sdk_enumerate_bypasses_application_container(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_runner(*, library_path: str | None = None) -> int:
        captured["library_path"] = library_path
        print(
            "[RusGuard SDK]\n"
            "library path: /tmp/librgsec.so\n"
            "library load ok\n"
            "initialize ok\n"
            "\n"
            "[USB_HID]\n"
            "find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo\n"
            "\n"
            "[SERIAL]\n"
            "find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo\n"
            "\n"
            "uninitialize ok"
        )
        return 0

    monkeypatch.setattr(cli_module, "run_rusguard_sdk_enumeration_command", _fake_runner)
    monkeypatch.setattr(
        cli_module,
        "create_bootstrapped_application_container",
        lambda _settings: (_ for _ in ()).throw(AssertionError("container should not be created")),
    )

    exit_code, stdout, stderr = _run_cli(
        ["rusguard-sdk-enumerate", "--library-path", "/tmp/librgsec.so"]
    )

    assert exit_code == 0
    assert captured["library_path"] == "/tmp/librgsec.so"
    assert "RusGuard SDK" in stdout
    assert "USB_HID" in stdout
    assert "SERIAL" in stdout
    assert stderr == ""


def test_command_skips_find_endpoints_and_reports_reason(monkeypatch) -> None:
    observed: list[object] = []

    class _RunnerSdk:
        def __init__(self, library_path: Path) -> None:
            observed.append(("init_sdk", library_path.as_posix()))
            self.library_path = library_path

        def initialize(self) -> None:
            observed.append("initialize")

        def find_endpoints(self, endpoint_type: int) -> int:
            raise AssertionError(f"RG_FindEndPoints must not be called: {endpoint_type}")

        def uninitialize(self) -> None:
            observed.append("uninitialize")

    monkeypatch.setattr("app.diagnostics.rusguard_sdk.CountOnlyRusGuardSdk", _RunnerSdk)

    stdout_buffer = StringIO()
    stderr_buffer = StringIO()

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = run_rusguard_sdk_enumeration_command(library_path="/tmp/librgsec.so")

    assert exit_code == 0
    assert stderr_buffer.getvalue() == ""
    assert stdout_buffer.getvalue() == (
        "[RusGuard SDK]\n"
        "library path: C:/tmp/librgsec.so\n"
        "library load ok\n"
        "initialize ok\n"
        "\n"
        "[USB_HID]\n"
        "find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo\n"
        "\n"
        "[SERIAL]\n"
        "find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo\n"
        "\n"
        "uninitialize ok\n"
    )
    assert observed == [
        ("init_sdk", "C:/tmp/librgsec.so"),
        "initialize",
        "uninitialize",
    ]


class _FakeSdk:
    def __init__(self) -> None:
        self.library_path = Path("/fake/librgsec.so")
        self.calls: list[object] = []

    def initialize(self) -> None:
        self.calls.append("initialize")

    def find_endpoints(self, endpoint_type: int) -> int:
        raise AssertionError(f"RG_FindEndPoints must not be called: {endpoint_type}")

    def uninitialize(self) -> None:
        self.calls.append("uninitialize")


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            exit_code = main(argv)
        except SystemExit as error:
            exit_code = int(error.code)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
