from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from app import cli as cli_module
from app.cli import main
from app.diagnostics.rusguard_sdk import (
    EndpointTypeContract,
    EnumeratedEndpoint,
    EnumeratedEndpointGroup,
    VendorAbiContract,
    enumerate_endpoints,
    load_vendor_abi_contract,
    render_report,
    run_rusguard_sdk_enumeration_command,
)


def test_render_report_uses_compact_grouped_sections() -> None:
    report = render_report(
        Path("/opt/rusguard/librgsec.so"),
        (
            EnumeratedEndpointGroup(
                queried_type="USB_HID",
                count=1,
                endpoints=(
                    EnumeratedEndpoint(
                        index=0,
                        type_name="USB_HID",
                        address="0",
                        friendly_name="RusGuard Reader",
                    ),
                ),
            ),
            EnumeratedEndpointGroup(
                queried_type="SERIAL",
                count=0,
                endpoints=(),
            ),
        ),
    )

    assert report == (
        "RusGuard SDK\n"
        "library: /opt/rusguard/librgsec.so\n"
        "\n"
        "[USB_HID]\n"
        "count: 1\n"
        "- index: 0, type: USB_HID, address: 0, friendly_name: RusGuard Reader\n"
        "\n"
        "[SERIAL]\n"
        "count: 0"
    )


def test_enumerate_endpoints_supports_count_only_when_endpoint_info_contract_is_missing() -> None:
    sdk = _FakeSdk(
        counts={200: 1, 100: 0},
        endpoint_map={},
    )
    contract = VendorAbiContract(
        endpoint_types=EndpointTypeContract(usb_hid=200, serial=100),
        endpoint_info=None,
    )

    groups = enumerate_endpoints(sdk, contract)

    assert sdk.calls == [
        "initialize",
        ("find_endpoints", 200),
        ("find_endpoints", 100),
        "uninitialize",
    ]
    assert groups == (
        EnumeratedEndpointGroup(
            queried_type="USB_HID",
            count=1,
            endpoints=(),
            endpoint_info_supported=False,
            unsupported_reason="endpoint info decoding unsupported due to missing vendor ABI contract",
        ),
        EnumeratedEndpointGroup(
            queried_type="SERIAL",
            count=0,
            endpoints=(),
        ),
    )
    assert sdk.uninitialized is True


def test_cli_rusguard_sdk_enumerate_bypasses_application_container(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_runner(*, library_path: str | None = None) -> int:
        captured["library_path"] = library_path
        print(
            "RusGuard SDK\n"
            "library: /tmp/librgsec.so\n"
            "\n"
            "USB_HID\n"
            "count: 0\n"
            "\n"
            "SERIAL\n"
            "count: 0"
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


def test_load_vendor_abi_contract_allows_count_only_enumeration_without_endpoint_info_abi() -> None:
    contract = load_vendor_abi_contract()

    assert contract == VendorAbiContract(
        endpoint_types=EndpointTypeContract(usb_hid=2, serial=1),
        endpoint_info=None,
    )


def test_command_proceeds_to_enumeration_without_endpoint_info_abi(monkeypatch) -> None:
    observed: list[object] = []

    class _RunnerSdk:
        def __init__(self, library_path: Path) -> None:
            observed.append(("init_sdk", library_path.as_posix()))

        def initialize(self) -> None:
            observed.append("initialize")

        def find_endpoints(self, endpoint_type: int) -> int:
            observed.append(("find_endpoints", endpoint_type))
            if endpoint_type == 2:
                return 1
            if endpoint_type == 1:
                return 0
            raise AssertionError(f"unexpected endpoint type: {endpoint_type}")

        def get_found_endpoint_info(self, endpoint_type_name: str, index: int) -> EnumeratedEndpoint:
            observed.append(("get_found_endpoint_info", endpoint_type_name, index))
            raise AssertionError("endpoint info lookup must not run without a proven ABI")

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
        "RusGuard SDK\n"
        "library: C:/tmp/librgsec.so\n"
        "\n"
        "[USB_HID]\n"
        "count: 1\n"
        "endpoint info decoding unsupported due to missing vendor ABI contract\n"
        "\n"
        "[SERIAL]\n"
        "count: 0\n"
    )
    assert observed == [
        ("init_sdk", "C:/tmp/librgsec.so"),
        "initialize",
        ("find_endpoints", 2),
        ("find_endpoints", 1),
        "uninitialize",
    ]


class _FakeSdk:
    def __init__(
        self,
        *,
        counts: dict[int, int],
        endpoint_map: dict[tuple[str, int], EnumeratedEndpoint],
    ) -> None:
        self.library_path = Path("/fake/librgsec.so")
        self._counts = counts
        self._endpoint_map = endpoint_map
        self.calls: list[object] = []
        self.uninitialized = False

    def initialize(self) -> None:
        self.calls.append("initialize")

    def find_endpoints(self, endpoint_type: int) -> int:
        self.calls.append(("find_endpoints", endpoint_type))
        return self._counts[endpoint_type]

    def get_found_endpoint_info(self, endpoint_type_name: str, index: int) -> EnumeratedEndpoint:
        self.calls.append(("get_found_endpoint_info", endpoint_type_name, index))
        return self._endpoint_map[(endpoint_type_name, index)]

    def uninitialize(self) -> None:
        self.calls.append("uninitialize")
        self.uninitialized = True


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            exit_code = main(argv)
        except SystemExit as error:
            exit_code = int(error.code)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
