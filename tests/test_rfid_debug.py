from __future__ import annotations

from app.hardware.rfid_debug import capture_rfid_serial_exchange
from app.hardware.transport_config import EndpointTimeoutSettings, RfidSerialTransportSettings


def test_capture_rfid_serial_exchange_collects_multiple_chunks() -> None:
    capture = capture_rfid_serial_exchange(
        settings=RfidSerialTransportSettings(
            transport="serial",
            port="/dev/ttyACM0",
            baudrate=9600,
            data_bits=8,
            parity="none",
            stop_bits=1,
        ),
        timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
        max_chunks=4,
        serial_module_loader=lambda: _FakeSerialModule([b"READ\n", b"UID:aa-bb cc\n", b""]),
    )

    assert capture.port == "/dev/ttyACM0"
    assert capture.chunk_count == 2
    assert capture.combined_lines == ("READ", "UID:aa-bb cc")
    assert capture.chunks[0].bytes_hex == "524541440A"
    assert capture.chunks[1].lines == ("UID:aa-bb cc",)


class _FakeSerialModule:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses

    def Serial(self, **kwargs):  # noqa: N802
        return _FakeSerialConnection(self._responses)


class _FakeSerialConnection:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.writes: list[bytes] = []

    def reset_input_buffer(self) -> None:
        return None

    def reset_output_buffer(self) -> None:
        return None

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

    def read_until(self, separator: bytes = b"\n") -> bytes:
        if not self._responses:
            return b""
        return self._responses.pop(0)

    def close(self) -> None:
        return None
