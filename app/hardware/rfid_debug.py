from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.hardware.transport_config import EndpointTimeoutSettings, RfidSerialTransportSettings


@dataclass(frozen=True, slots=True)
class RfidDebugChunk:
    index: int
    bytes_hex: str
    bytes_ascii: str
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RfidSerialExchangeCapture:
    port: str
    request_ascii: str
    request_hex: str
    max_chunks: int
    chunk_count: int
    combined_hex: str
    combined_ascii: str
    combined_lines: tuple[str, ...]
    chunks: tuple[RfidDebugChunk, ...]


def capture_rfid_serial_exchange(
    *,
    settings: RfidSerialTransportSettings,
    timeouts: EndpointTimeoutSettings,
    request: bytes = b"READ\n",
    max_chunks: int = 4,
    serial_module_loader: Callable[[], Any] | None = None,
) -> RfidSerialExchangeCapture:
    if max_chunks < 1:
        raise ValueError("max_chunks must be at least 1")
    serial_module = (serial_module_loader or _load_serial_module)()
    connection = None
    start = time.monotonic()
    chunks: list[bytes] = []
    try:
        connection = serial_module.Serial(
            port=settings.port,
            baudrate=settings.baudrate,
            bytesize=settings.data_bits,
            parity=_serial_parity(settings.parity),
            stopbits=settings.stop_bits,
            timeout=timeouts.read_timeout_ms / 1000,
            write_timeout=timeouts.write_timeout_ms / 1000,
        )
        if (time.monotonic() - start) * 1000 > timeouts.connect_timeout_ms:
            raise TimeoutError("Serial transport open timed out.")
        if hasattr(connection, "reset_input_buffer"):
            connection.reset_input_buffer()
        if hasattr(connection, "reset_output_buffer"):
            connection.reset_output_buffer()
        connection.write(request)
        for _ in range(max_chunks):
            chunk = connection.read_until(b"\n")
            if not chunk:
                break
            chunks.append(bytes(chunk))
    except ModuleNotFoundError as error:
        raise OSError("pyserial dependency is not available.") from error
    except TimeoutError:
        raise
    except OSError:
        raise
    except Exception as error:
        raise OSError(f"RFID debug capture failed: {error}") from error
    finally:
        if connection is not None and hasattr(connection, "close"):
            connection.close()
    combined = b"".join(chunks)
    return RfidSerialExchangeCapture(
        port=settings.port,
        request_ascii=_safe_ascii(request),
        request_hex=request.hex().upper(),
        max_chunks=max_chunks,
        chunk_count=len(chunks),
        combined_hex=combined.hex().upper(),
        combined_ascii=_safe_ascii(combined),
        combined_lines=tuple(line.strip() for line in _safe_ascii(combined).splitlines() if line.strip()),
        chunks=tuple(
            RfidDebugChunk(
                index=index,
                bytes_hex=chunk.hex().upper(),
                bytes_ascii=_safe_ascii(chunk),
                lines=tuple(line.strip() for line in _safe_ascii(chunk).splitlines() if line.strip()),
            )
            for index, chunk in enumerate(chunks)
        ),
    )


def _load_serial_module() -> Any:
    return importlib.import_module("serial")


def _serial_parity(parity: str) -> str:
    if parity == "none":
        return "N"
    if parity == "even":
        return "E"
    return "O"


def _safe_ascii(payload: bytes) -> str:
    return payload.decode("ascii", errors="backslashreplace")
