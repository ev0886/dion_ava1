from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from app import cli as cli_module
from app.cli import main
from app.diagnostics.rusguard_sdk import (
    AcmProbeDiagnosticReport,
    AcmStatusNoMaskDiagnosticReport,
    DiagnosticReport,
    DiagnosticSection,
    EndpointInfo,
    OperationResult,
    RG_ENDPOINT_TYPE_SERIAL,
    RG_ENDPOINT_TYPE_USB_HID,
    AcmProbeDiagnosticResult,
    AcmStatusNoMaskDiagnosticResult,
    decode_api_error,
    render_acm_probe_report,
    render_acm_status_no_mask_report,
    render_report,
    render_serial_open_report,
    run_acm_probe_diagnostic,
    run_acm_status_no_mask_diagnostic,
    run_rusguard_sdk_acm_probe_command,
    run_rusguard_sdk_acm_status_no_mask_command,
    run_rusguard_sdk_enumeration_command,
    run_rusguard_sdk_serial_open_diagnostic_command,
    run_safe_diagnostic,
    run_serial_open_diagnostic,
    SerialEndpointDiagnosticResult,
    SerialOpenDiagnosticReport,
)


def test_render_report_shows_real_discovery_sections() -> None:
    report = render_report(
        DiagnosticReport(
            library_path=Path("/opt/rusguard/librgsec.so"),
            sections=(
                DiagnosticSection(
                    title="USB_HID",
                    lines=(
                        "count: 2",
                        "- index: 0, type: 1, address: hidraw0, friendly_name: R5 USB #0",
                        "- index: 1, type: 1, address: hidraw1, friendly_name: R5 USB #1",
                    ),
                ),
                DiagnosticSection(
                    title="SERIAL",
                    lines=("count: 0",),
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
        "count: 2\n"
        "- index: 0, type: 1, address: hidraw0, friendly_name: R5 USB #0\n"
        "- index: 1, type: 1, address: hidraw1, friendly_name: R5 USB #1\n"
        "\n"
        "[SERIAL]\n"
        "count: 0\n"
        "\n"
        "uninitialize ok"
    )


def test_run_safe_diagnostic_discovers_usb_and_serial_endpoints() -> None:
    sdk = _FakeSdk()

    report = run_safe_diagnostic(sdk)

    assert sdk.calls == [
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_USB_HID),
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        "uninitialize",
    ]
    assert report == DiagnosticReport(
        library_path=Path("/fake/librgsec.so"),
        sections=(
            DiagnosticSection(
                title="USB_HID",
                lines=(
                    "count: 2",
                    "- index: 0, type: 1, address: hidraw0, friendly_name: R5 USB #0",
                    "- index: 1, type: 1, address: hidraw1, friendly_name: R5 USB #1",
                ),
            ),
            DiagnosticSection(
                title="SERIAL",
                lines=(
                    "count: 2",
                    "- index: 0, type: 2, address: /dev/ttyUSB0, friendly_name: USB Serial Reader",
                    "- index: 1, type: 2, address: /dev/ttyACM0, friendly_name: RusGuard Reader",
                ),
            ),
        ),
    )


def test_render_serial_open_report_shows_endpoint_probe_results() -> None:
    report = render_serial_open_report(
        SerialOpenDiagnosticReport(
            library_path=Path("/opt/rusguard/librgsec.so"),
            serial_results=(
                SerialEndpointDiagnosticResult(
                    endpoint_info=EndpointInfo(index=0, type=2, address="/dev/ttyUSB0", friendly_name=""),
                    open_ok=True,
                    open_code=0,
                    open_code_name="EC_OK",
                    open_code_message="all good",
                    status_ok=True,
                    status_code=0,
                ),
                SerialEndpointDiagnosticResult(
                    endpoint_info=EndpointInfo(index=1, type=2, address="/dev/ttyUSB1", friendly_name=""),
                    open_ok=False,
                    open_code=27,
                    open_code_name="EC_IO_OPEN_FAIL",
                    open_code_message="connection open failed",
                    status_ok=None,
                    status_code=None,
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
        "[SERIAL]\n"
        "count: 2\n"
        "- index: 0, address: /dev/ttyUSB0, open: ok, status: ok\n"
        "- index: 1, address: /dev/ttyUSB1, open: fail(code=27, name=EC_IO_OPEN_FAIL, message=connection open failed)\n"
        "\n"
        "uninitialize ok"
    )


def test_run_serial_open_diagnostic_probes_discovered_serial_endpoints() -> None:
    sdk = _FakeSdk()

    report = run_serial_open_diagnostic(sdk)

    assert sdk.calls == [
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        ("diagnose_serial_endpoint", 0, "/dev/ttyUSB0"),
        ("diagnose_serial_endpoint", 1, "/dev/ttyACM0"),
        "uninitialize",
    ]
    assert report == SerialOpenDiagnosticReport(
        library_path=Path("/fake/librgsec.so"),
        serial_results=(
            SerialEndpointDiagnosticResult(
                endpoint_info=EndpointInfo(index=0, type=2, address="/dev/ttyUSB0", friendly_name="USB Serial Reader"),
                open_ok=True,
                open_code=0,
                open_code_name="EC_OK",
                open_code_message="all good",
                status_ok=True,
                status_code=0,
            ),
            SerialEndpointDiagnosticResult(
                endpoint_info=EndpointInfo(index=1, type=2, address="/dev/ttyACM0", friendly_name="RusGuard Reader"),
                open_ok=True,
                open_code=0,
                open_code_name="EC_OK",
                open_code_message="all good",
                status_ok=True,
                status_code=0,
            ),
        ),
    )


def test_render_acm_probe_report_shows_vendor_sequence_results() -> None:
    report = render_acm_probe_report(
        AcmProbeDiagnosticReport(
            library_path=Path("/opt/rusguard/librgsec.so"),
            target_endpoint="/dev/ttyACM0",
            found=True,
            result=AcmProbeDiagnosticResult(
                endpoint_info=EndpointInfo(index=0, type=2, address="/dev/ttyACM0", friendly_name="RusGuard Reader"),
                open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
                set_cards_mask_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
                status_result=OperationResult(
                    ok=False,
                    code=11,
                    code_name="EC_DEVICE_NO_RESPOND",
                    code_message="device does not respond to requests",
                ),
                close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            ),
        )
    )

    assert report == (
        "[RusGuard SDK]\n"
        "library path: /opt/rusguard/librgsec.so\n"
        "library load ok\n"
        "initialize ok\n"
        "\n"
        "[ACM]\n"
        "target: /dev/ttyACM0\n"
        "open: ok\n"
        "set_cards_mask: ok\n"
        "status: fail(code=11, name=EC_DEVICE_NO_RESPOND, message=device does not respond to requests)\n"
        "close: ok\n"
        "\n"
        "uninitialize ok"
    )


def test_run_acm_probe_diagnostic_only_targets_exact_ttyacm0() -> None:
    sdk = _FakeSdk()

    report = run_acm_probe_diagnostic(sdk)

    assert sdk.calls == [
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        ("diagnose_acm_endpoint", 1, "/dev/ttyACM0"),
        "uninitialize",
    ]
    assert report == AcmProbeDiagnosticReport(
        library_path=Path("/fake/librgsec.so"),
        target_endpoint="/dev/ttyACM0",
        found=True,
        result=AcmProbeDiagnosticResult(
            endpoint_info=EndpointInfo(index=1, type=2, address="/dev/ttyACM0", friendly_name="RusGuard Reader"),
            open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            set_cards_mask_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            status_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
        ),
    )


def test_run_acm_probe_diagnostic_reports_missing_target_cleanly() -> None:
    sdk = _AcmMissingSdk()

    report = run_acm_probe_diagnostic(sdk)

    assert sdk.calls == [
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        "uninitialize",
    ]
    assert report == AcmProbeDiagnosticReport(
        library_path=Path("/fake/librgsec.so"),
        target_endpoint="/dev/ttyACM0",
        found=False,
        result=None,
    )


def test_render_acm_status_no_mask_report_shows_direct_status_probe_results() -> None:
    report = render_acm_status_no_mask_report(
        AcmStatusNoMaskDiagnosticReport(
            library_path=Path("/opt/rusguard/librgsec.so"),
            target_endpoint="/dev/ttyACM0",
            found=True,
            result=AcmStatusNoMaskDiagnosticResult(
                endpoint_info=EndpointInfo(index=0, type=2, address="/dev/ttyACM0", friendly_name="RusGuard Reader"),
                open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
                status_result=OperationResult(
                    ok=False,
                    code=12,
                    code_name="EC_DEVICE_COMM_FAILURE",
                    code_message="device communication failure",
                ),
                close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            ),
        )
    )

    assert report == (
        "[RusGuard SDK]\n"
        "library path: /opt/rusguard/librgsec.so\n"
        "library load ok\n"
        "initialize ok\n"
        "\n"
        "[ACM]\n"
        "target: /dev/ttyACM0\n"
        "open: ok\n"
        "status: fail(code=12, name=EC_DEVICE_COMM_FAILURE, message=device communication failure)\n"
        "close: ok\n"
        "\n"
        "uninitialize ok"
    )


def test_run_acm_status_no_mask_diagnostic_only_targets_exact_ttyacm0() -> None:
    sdk = _FakeSdk()

    report = run_acm_status_no_mask_diagnostic(sdk)

    assert sdk.calls == [
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        ("diagnose_acm_status_no_mask_endpoint", 1, "/dev/ttyACM0"),
        "uninitialize",
    ]
    assert report == AcmStatusNoMaskDiagnosticReport(
        library_path=Path("/fake/librgsec.so"),
        target_endpoint="/dev/ttyACM0",
        found=True,
        result=AcmStatusNoMaskDiagnosticResult(
            endpoint_info=EndpointInfo(index=1, type=2, address="/dev/ttyACM0", friendly_name="RusGuard Reader"),
            open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            status_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
        ),
    )


def test_run_acm_status_no_mask_diagnostic_reports_missing_target_cleanly() -> None:
    sdk = _AcmMissingSdk()

    report = run_acm_status_no_mask_diagnostic(sdk)

    assert sdk.calls == [
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        "uninitialize",
    ]
    assert report == AcmStatusNoMaskDiagnosticReport(
        library_path=Path("/fake/librgsec.so"),
        target_endpoint="/dev/ttyACM0",
        found=False,
        result=None,
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
            "count: 0\n"
            "\n"
            "[SERIAL]\n"
            "count: 0\n"
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


def test_cli_rusguard_sdk_serial_open_diagnostic_bypasses_application_container(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_runner(*, library_path: str | None = None) -> int:
        captured["library_path"] = library_path
        print(
            "[RusGuard SDK]\n"
            "library path: /tmp/librgsec.so\n"
            "library load ok\n"
            "initialize ok\n"
            "\n"
            "[SERIAL]\n"
            "count: 1\n"
            "- index: 0, address: /dev/ttyUSB0, open: ok, status: ok\n"
            "\n"
            "uninitialize ok"
        )
        return 0

    monkeypatch.setattr(cli_module, "run_rusguard_sdk_serial_open_diagnostic_command", _fake_runner)
    monkeypatch.setattr(
        cli_module,
        "create_bootstrapped_application_container",
        lambda _settings: (_ for _ in ()).throw(AssertionError("container should not be created")),
    )

    exit_code, stdout, stderr = _run_cli(
        ["rusguard-sdk-serial-open-diagnostic", "--library-path", "/tmp/librgsec.so"]
    )

    assert exit_code == 0
    assert captured["library_path"] == "/tmp/librgsec.so"
    assert "SERIAL" in stdout
    assert "open: ok" in stdout
    assert stderr == ""


def test_cli_rusguard_sdk_acm_probe_bypasses_application_container(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_runner(*, library_path: str | None = None) -> int:
        captured["library_path"] = library_path
        print(
            "[RusGuard SDK]\n"
            "library path: /tmp/librgsec.so\n"
            "library load ok\n"
            "initialize ok\n"
            "\n"
            "[ACM]\n"
            "target: /dev/ttyACM0\n"
            "open: ok\n"
            "set_cards_mask: ok\n"
            "status: ok\n"
            "close: ok\n"
            "\n"
            "uninitialize ok"
        )
        return 0

    monkeypatch.setattr(cli_module, "run_rusguard_sdk_acm_probe_command", _fake_runner)
    monkeypatch.setattr(
        cli_module,
        "create_bootstrapped_application_container",
        lambda _settings: (_ for _ in ()).throw(AssertionError("container should not be created")),
    )

    exit_code, stdout, stderr = _run_cli(
        ["rusguard-sdk-acm-probe", "--library-path", "/tmp/librgsec.so"]
    )

    assert exit_code == 0
    assert captured["library_path"] == "/tmp/librgsec.so"
    assert "[ACM]" in stdout
    assert "target: /dev/ttyACM0" in stdout
    assert stderr == ""


def test_cli_rusguard_sdk_acm_status_no_mask_bypasses_application_container(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_runner(*, library_path: str | None = None) -> int:
        captured["library_path"] = library_path
        print(
            "[RusGuard SDK]\n"
            "library path: /tmp/librgsec.so\n"
            "library load ok\n"
            "initialize ok\n"
            "\n"
            "[ACM]\n"
            "target: /dev/ttyACM0\n"
            "open: ok\n"
            "status: ok\n"
            "close: ok\n"
            "\n"
            "uninitialize ok"
        )
        return 0

    monkeypatch.setattr(cli_module, "run_rusguard_sdk_acm_status_no_mask_command", _fake_runner)
    monkeypatch.setattr(
        cli_module,
        "create_bootstrapped_application_container",
        lambda _settings: (_ for _ in ()).throw(AssertionError("container should not be created")),
    )

    exit_code, stdout, stderr = _run_cli(
        ["rusguard-sdk-acm-status-no-mask", "--library-path", "/tmp/librgsec.so"]
    )

    assert exit_code == 0
    assert captured["library_path"] == "/tmp/librgsec.so"
    assert "[ACM]" in stdout
    assert "target: /dev/ttyACM0" in stdout
    assert "status: ok" in stdout
    assert stderr == ""


def test_command_runs_real_discovery_flow(monkeypatch) -> None:
    observed: list[object] = []

    class _RunnerSdk:
        def __init__(self, library_path: Path) -> None:
            observed.append(("init_sdk", library_path.as_posix()))
            self.library_path = library_path

        def initialize(self) -> None:
            observed.append("initialize")

        def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]:
            observed.append(("find_endpoint_infos", endpoint_type_mask))
            if endpoint_type_mask == RG_ENDPOINT_TYPE_USB_HID:
                return (
                    EndpointInfo(index=0, type=1, address="hidraw0", friendly_name="R5 USB #0"),
                )
            if endpoint_type_mask == RG_ENDPOINT_TYPE_SERIAL:
                return ()
            raise AssertionError(f"unexpected endpoint type mask: {endpoint_type_mask}")

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
        "count: 1\n"
        "- index: 0, type: 1, address: hidraw0, friendly_name: R5 USB #0\n"
        "\n"
        "[SERIAL]\n"
        "count: 0\n"
        "\n"
        "uninitialize ok\n"
    )
    assert observed == [
        ("init_sdk", "C:/tmp/librgsec.so"),
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_USB_HID),
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        "uninitialize",
    ]


def test_serial_open_command_runs_real_probe_flow(monkeypatch) -> None:
    observed: list[object] = []

    class _RunnerSdk:
        def __init__(self, library_path: Path) -> None:
            observed.append(("init_sdk", library_path.as_posix()))
            self.library_path = library_path

        def initialize(self) -> None:
            observed.append("initialize")

        def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]:
            observed.append(("find_endpoint_infos", endpoint_type_mask))
            if endpoint_type_mask == RG_ENDPOINT_TYPE_SERIAL:
                return (
                    EndpointInfo(index=0, type=2, address="/dev/ttyUSB0", friendly_name=""),
                    EndpointInfo(index=1, type=2, address="/dev/ttyUSB1", friendly_name=""),
                )
            raise AssertionError(f"unexpected endpoint type mask: {endpoint_type_mask}")

        def diagnose_serial_endpoint(self, endpoint_info: EndpointInfo) -> SerialEndpointDiagnosticResult:
            observed.append(("diagnose_serial_endpoint", endpoint_info.index, endpoint_info.address))
            return SerialEndpointDiagnosticResult(
                endpoint_info=endpoint_info,
                open_ok=endpoint_info.index == 0,
                open_code=0 if endpoint_info.index == 0 else 27,
                open_code_name="EC_OK" if endpoint_info.index == 0 else "EC_IO_OPEN_FAIL",
                open_code_message="all good" if endpoint_info.index == 0 else "connection open failed",
                status_ok=True if endpoint_info.index == 0 else None,
                status_code=0 if endpoint_info.index == 0 else None,
            )

        def uninitialize(self) -> None:
            observed.append("uninitialize")

    monkeypatch.setattr("app.diagnostics.rusguard_sdk.CountOnlyRusGuardSdk", _RunnerSdk)

    stdout_buffer = StringIO()
    stderr_buffer = StringIO()

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = run_rusguard_sdk_serial_open_diagnostic_command(library_path="/tmp/librgsec.so")

    assert exit_code == 0
    assert stderr_buffer.getvalue() == ""
    assert stdout_buffer.getvalue() == (
        "[RusGuard SDK]\n"
        "library path: C:/tmp/librgsec.so\n"
        "library load ok\n"
        "initialize ok\n"
        "\n"
        "[SERIAL]\n"
        "count: 2\n"
        "- index: 0, address: /dev/ttyUSB0, open: ok, status: ok\n"
        "- index: 1, address: /dev/ttyUSB1, open: fail(code=27, name=EC_IO_OPEN_FAIL, message=connection open failed)\n"
        "\n"
        "uninitialize ok\n"
    )
    assert observed == [
        ("init_sdk", "C:/tmp/librgsec.so"),
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        ("diagnose_serial_endpoint", 0, "/dev/ttyUSB0"),
        ("diagnose_serial_endpoint", 1, "/dev/ttyUSB1"),
        "uninitialize",
    ]


def test_acm_probe_command_runs_exact_target_probe_flow(monkeypatch) -> None:
    observed: list[object] = []

    class _RunnerSdk:
        def __init__(self, library_path: Path) -> None:
            observed.append(("init_sdk", library_path.as_posix()))
            self.library_path = library_path

        def initialize(self) -> None:
            observed.append("initialize")

        def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]:
            observed.append(("find_endpoint_infos", endpoint_type_mask))
            if endpoint_type_mask == RG_ENDPOINT_TYPE_SERIAL:
                return (
                    EndpointInfo(index=0, type=2, address="/dev/ttyUSB0", friendly_name="other"),
                    EndpointInfo(index=1, type=2, address="/dev/ttyACM0", friendly_name="reader"),
                    EndpointInfo(index=2, type=2, address="/dev/ttyUSB1", friendly_name="other"),
                )
            raise AssertionError(f"unexpected endpoint type mask: {endpoint_type_mask}")

        def diagnose_acm_endpoint(self, endpoint_info: EndpointInfo) -> AcmProbeDiagnosticResult:
            observed.append(("diagnose_acm_endpoint", endpoint_info.index, endpoint_info.address))
            return AcmProbeDiagnosticResult(
                endpoint_info=endpoint_info,
                open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
                set_cards_mask_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
                status_result=OperationResult(
                    ok=False,
                    code=11,
                    code_name="EC_DEVICE_NO_RESPOND",
                    code_message="device does not respond to requests",
                ),
                close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            )

        def uninitialize(self) -> None:
            observed.append("uninitialize")

    monkeypatch.setattr("app.diagnostics.rusguard_sdk.CountOnlyRusGuardSdk", _RunnerSdk)

    stdout_buffer = StringIO()
    stderr_buffer = StringIO()

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = run_rusguard_sdk_acm_probe_command(library_path="/tmp/librgsec.so")

    assert exit_code == 0
    assert stderr_buffer.getvalue() == ""
    assert stdout_buffer.getvalue() == (
        "[RusGuard SDK]\n"
        "library path: C:/tmp/librgsec.so\n"
        "library load ok\n"
        "initialize ok\n"
        "\n"
        "[ACM]\n"
        "target: /dev/ttyACM0\n"
        "open: ok\n"
        "set_cards_mask: ok\n"
        "status: fail(code=11, name=EC_DEVICE_NO_RESPOND, message=device does not respond to requests)\n"
        "close: ok\n"
        "\n"
        "uninitialize ok\n"
    )
    assert observed == [
        ("init_sdk", "C:/tmp/librgsec.so"),
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        ("diagnose_acm_endpoint", 1, "/dev/ttyACM0"),
        "uninitialize",
    ]


def test_acm_status_no_mask_command_runs_exact_target_probe_flow(monkeypatch) -> None:
    observed: list[object] = []

    class _RunnerSdk:
        def __init__(self, library_path: Path) -> None:
            observed.append(("init_sdk", library_path.as_posix()))
            self.library_path = library_path

        def initialize(self) -> None:
            observed.append("initialize")

        def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]:
            observed.append(("find_endpoint_infos", endpoint_type_mask))
            if endpoint_type_mask == RG_ENDPOINT_TYPE_SERIAL:
                return (
                    EndpointInfo(index=0, type=2, address="/dev/ttyUSB0", friendly_name="other"),
                    EndpointInfo(index=1, type=2, address="/dev/ttyACM0", friendly_name="reader"),
                    EndpointInfo(index=2, type=2, address="/dev/ttyUSB1", friendly_name="other"),
                )
            raise AssertionError(f"unexpected endpoint type mask: {endpoint_type_mask}")

        def diagnose_acm_status_no_mask_endpoint(self, endpoint_info: EndpointInfo) -> AcmStatusNoMaskDiagnosticResult:
            observed.append(("diagnose_acm_status_no_mask_endpoint", endpoint_info.index, endpoint_info.address))
            return AcmStatusNoMaskDiagnosticResult(
                endpoint_info=endpoint_info,
                open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
                status_result=OperationResult(
                    ok=False,
                    code=12,
                    code_name="EC_DEVICE_COMM_FAILURE",
                    code_message="device communication failure",
                ),
                close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            )

        def uninitialize(self) -> None:
            observed.append("uninitialize")

    monkeypatch.setattr("app.diagnostics.rusguard_sdk.CountOnlyRusGuardSdk", _RunnerSdk)

    stdout_buffer = StringIO()
    stderr_buffer = StringIO()

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = run_rusguard_sdk_acm_status_no_mask_command(library_path="/tmp/librgsec.so")

    assert exit_code == 0
    assert stderr_buffer.getvalue() == ""
    assert stdout_buffer.getvalue() == (
        "[RusGuard SDK]\n"
        "library path: C:/tmp/librgsec.so\n"
        "library load ok\n"
        "initialize ok\n"
        "\n"
        "[ACM]\n"
        "target: /dev/ttyACM0\n"
        "open: ok\n"
        "status: fail(code=12, name=EC_DEVICE_COMM_FAILURE, message=device communication failure)\n"
        "close: ok\n"
        "\n"
        "uninitialize ok\n"
    )
    assert observed == [
        ("init_sdk", "C:/tmp/librgsec.so"),
        "initialize",
        ("find_endpoint_infos", RG_ENDPOINT_TYPE_SERIAL),
        ("diagnose_acm_status_no_mask_endpoint", 1, "/dev/ttyACM0"),
        "uninitialize",
    ]


class _FakeSdk:
    def __init__(self) -> None:
        self.library_path = Path("/fake/librgsec.so")
        self.calls: list[object] = []

    def initialize(self) -> None:
        self.calls.append("initialize")

    def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]:
        self.calls.append(("find_endpoint_infos", endpoint_type_mask))
        if endpoint_type_mask == RG_ENDPOINT_TYPE_USB_HID:
            return (
                EndpointInfo(index=0, type=1, address="hidraw0", friendly_name="R5 USB #0"),
                EndpointInfo(index=1, type=1, address="hidraw1", friendly_name="R5 USB #1"),
            )
        if endpoint_type_mask == RG_ENDPOINT_TYPE_SERIAL:
            return (
                EndpointInfo(index=0, type=2, address="/dev/ttyUSB0", friendly_name="USB Serial Reader"),
                EndpointInfo(index=1, type=2, address="/dev/ttyACM0", friendly_name="RusGuard Reader"),
            )
        raise AssertionError(f"unexpected endpoint type mask: {endpoint_type_mask}")

    def uninitialize(self) -> None:
        self.calls.append("uninitialize")

    def diagnose_serial_endpoint(self, endpoint_info: EndpointInfo) -> SerialEndpointDiagnosticResult:
        self.calls.append(("diagnose_serial_endpoint", endpoint_info.index, endpoint_info.address))
        return SerialEndpointDiagnosticResult(
            endpoint_info=endpoint_info,
            open_ok=True,
            open_code=0,
            open_code_name="EC_OK",
            open_code_message="all good",
            status_ok=True,
            status_code=0,
        )

    def diagnose_acm_endpoint(self, endpoint_info: EndpointInfo) -> AcmProbeDiagnosticResult:
        self.calls.append(("diagnose_acm_endpoint", endpoint_info.index, endpoint_info.address))
        return AcmProbeDiagnosticResult(
            endpoint_info=endpoint_info,
            open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            set_cards_mask_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            status_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
        )

    def diagnose_acm_status_no_mask_endpoint(self, endpoint_info: EndpointInfo) -> AcmStatusNoMaskDiagnosticResult:
        self.calls.append(("diagnose_acm_status_no_mask_endpoint", endpoint_info.index, endpoint_info.address))
        return AcmStatusNoMaskDiagnosticResult(
            endpoint_info=endpoint_info,
            open_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            status_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
            close_result=OperationResult(ok=True, code=0, code_name="EC_OK", code_message="all good"),
        )


class _AcmMissingSdk:
    def __init__(self) -> None:
        self.library_path = Path("/fake/librgsec.so")
        self.calls: list[object] = []

    def initialize(self) -> None:
        self.calls.append("initialize")

    def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]:
        self.calls.append(("find_endpoint_infos", endpoint_type_mask))
        if endpoint_type_mask == RG_ENDPOINT_TYPE_SERIAL:
            return (
                EndpointInfo(index=0, type=2, address="/dev/ttyUSB0", friendly_name="USB Serial Reader"),
            )
        raise AssertionError(f"unexpected endpoint type mask: {endpoint_type_mask}")

    def uninitialize(self) -> None:
        self.calls.append("uninitialize")

    def diagnose_serial_endpoint(self, endpoint_info: EndpointInfo) -> SerialEndpointDiagnosticResult:
        raise AssertionError(f"unexpected serial endpoint probe: {endpoint_info}")

    def diagnose_acm_endpoint(self, endpoint_info: EndpointInfo) -> AcmProbeDiagnosticResult:
        raise AssertionError(f"unexpected acm endpoint probe: {endpoint_info}")

    def diagnose_acm_status_no_mask_endpoint(self, endpoint_info: EndpointInfo) -> AcmStatusNoMaskDiagnosticResult:
        raise AssertionError(f"unexpected acm no-mask endpoint probe: {endpoint_info}")


def test_decode_api_error_returns_vendor_defined_name_and_message() -> None:
    assert decode_api_error(11) == ("EC_DEVICE_NO_RESPOND", "device does not respond to requests")
    assert decode_api_error(999) == ("UNKNOWN_API_ERROR", "unknown RusGuard SDK error")


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            exit_code = main(argv)
        except SystemExit as error:
            exit_code = int(error.code)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
