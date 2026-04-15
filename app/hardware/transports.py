from __future__ import annotations

import importlib
import socket
import time
from typing import Any, Callable, Protocol, runtime_checkable

from app.hardware.transport_config import EndpointTimeoutSettings, SerialTransportSettings, TcpTransportSettings


@runtime_checkable
class SerialRequestResponseTransport(Protocol):
    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes: ...

    def send(self, payload: bytes) -> None: ...

    def request_sequence(
        self,
        payloads: list[bytes],
        *,
        timeout_ms: int | None = None,
        response_timeouts_ms: list[int] | None = None,
        frame_gap_timeout_ms: int | None = None,
    ) -> list[bytes]: ...


@runtime_checkable
class TcpRequestResponseTransport(Protocol):
    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes: ...


class SerialTransport:
    def __init__(
        self,
        *,
        settings: SerialTransportSettings,
        timeouts: EndpointTimeoutSettings,
        serial_module_loader: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._timeouts = timeouts
        self._serial_module_loader = serial_module_loader or _load_serial_module

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        effective_read_timeout_ms = timeout_ms if timeout_ms is not None else self._timeouts.read_timeout_ms
        connection = None
        start = time.monotonic()
        try:
            serial_module = self._serial_module_loader()
            connection = serial_module.Serial(
                port=self._settings.port,
                baudrate=self._settings.baudrate,
                bytesize=self._settings.data_bits,
                parity=_serial_parity(self._settings.parity),
                stopbits=self._settings.stop_bits,
                timeout=effective_read_timeout_ms / 1000,
                write_timeout=self._timeouts.write_timeout_ms / 1000,
            )
            if (time.monotonic() - start) * 1000 > self._timeouts.connect_timeout_ms:
                raise TimeoutError("Serial transport open timed out.")
            if hasattr(connection, "reset_input_buffer"):
                connection.reset_input_buffer()
            if hasattr(connection, "reset_output_buffer"):
                connection.reset_output_buffer()
            connection.write(payload)
            response = _read_serial_response(connection)
            if not response:
                raise TimeoutError("Serial transport read timed out.")
            return response
        except ModuleNotFoundError as error:
            raise OSError("pyserial dependency is not available.") from error
        except TimeoutError:
            raise
        except OSError:
            raise
        except Exception as error:
            raise OSError(f"Serial transport request failed: {error}") from error
        finally:
            if connection is not None and hasattr(connection, "close"):
                connection.close()

    def send(self, payload: bytes) -> None:
        connection = None
        start = time.monotonic()
        try:
            serial_module = self._serial_module_loader()
            connection = serial_module.Serial(
                port=self._settings.port,
                baudrate=self._settings.baudrate,
                bytesize=self._settings.data_bits,
                parity=_serial_parity(self._settings.parity),
                stopbits=self._settings.stop_bits,
                timeout=self._timeouts.read_timeout_ms / 1000,
                write_timeout=self._timeouts.write_timeout_ms / 1000,
            )
            if (time.monotonic() - start) * 1000 > self._timeouts.connect_timeout_ms:
                raise TimeoutError("Serial transport open timed out.")
            if hasattr(connection, "reset_input_buffer"):
                connection.reset_input_buffer()
            if hasattr(connection, "reset_output_buffer"):
                connection.reset_output_buffer()
            connection.write(payload)
        except ModuleNotFoundError as error:
            raise OSError("pyserial dependency is not available.") from error
        except TimeoutError:
            raise
        except OSError:
            raise
        except Exception as error:
            raise OSError(f"Serial transport send failed: {error}") from error
        finally:
            if connection is not None and hasattr(connection, "close"):
                connection.close()

    def request_sequence(
        self,
        payloads: list[bytes],
        *,
        timeout_ms: int | None = None,
        response_timeouts_ms: list[int] | None = None,
        frame_gap_timeout_ms: int | None = None,
    ) -> list[bytes]:
        if not payloads:
            return []
        effective_read_timeout_ms = timeout_ms if timeout_ms is not None else self._timeouts.read_timeout_ms
        per_response_timeouts_ms = response_timeouts_ms or [effective_read_timeout_ms] * len(payloads)
        if len(per_response_timeouts_ms) != len(payloads):
            raise ValueError("response_timeouts_ms length must match payload count")
        connection = None
        start = time.monotonic()
        responses: list[bytes] = []
        try:
            serial_module = self._serial_module_loader()
            connection = serial_module.Serial(
                port=self._settings.port,
                baudrate=self._settings.baudrate,
                bytesize=self._settings.data_bits,
                parity=_serial_parity(self._settings.parity),
                stopbits=self._settings.stop_bits,
                timeout=effective_read_timeout_ms / 1000,
                write_timeout=self._timeouts.write_timeout_ms / 1000,
            )
            if (time.monotonic() - start) * 1000 > self._timeouts.connect_timeout_ms:
                raise TimeoutError("Serial transport open timed out.")
            if hasattr(connection, "reset_input_buffer"):
                connection.reset_input_buffer()
            if hasattr(connection, "reset_output_buffer"):
                connection.reset_output_buffer()
            for payload, response_timeout_ms in zip(payloads, per_response_timeouts_ms, strict=True):
                connection.write(payload)
                if hasattr(connection, "flush"):
                    connection.flush()
                if hasattr(connection, "timeout"):
                    connection.timeout = response_timeout_ms / 1000
                response = _read_serial_response(connection, inter_byte_timeout_ms=frame_gap_timeout_ms)
                if not response:
                    raise TimeoutError("Serial transport read timed out.")
                responses.append(response)
            return responses
        except ModuleNotFoundError as error:
            raise OSError("pyserial dependency is not available.") from error
        except TimeoutError:
            raise
        except OSError:
            raise
        except Exception as error:
            raise OSError(f"Serial transport request sequence failed: {error}") from error
        finally:
            if connection is not None and hasattr(connection, "close"):
                connection.close()


class TcpTransport:
    def __init__(
        self,
        *,
        settings: TcpTransportSettings,
        timeouts: EndpointTimeoutSettings,
        socket_factory: Callable[[tuple[str, int], float], socket.socket] | None = None,
    ) -> None:
        self._settings = settings
        self._timeouts = timeouts
        self._socket_factory = socket_factory or socket.create_connection

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        effective_read_timeout_ms = timeout_ms if timeout_ms is not None else self._timeouts.read_timeout_ms
        sock = None
        try:
            sock = self._socket_factory(
                (self._settings.host, self._settings.port),
                self._timeouts.connect_timeout_ms / 1000,
            )
            sock.settimeout(self._timeouts.write_timeout_ms / 1000)
            sock.sendall(payload)
            sock.settimeout(effective_read_timeout_ms / 1000)
            return _recv_until_newline(sock)
        except TimeoutError:
            raise
        except OSError:
            raise
        except Exception as error:
            raise OSError(f"TCP transport request failed: {error}") from error
        finally:
            if sock is not None:
                sock.close()


class SerialTransportSkeleton:
    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        raise NotImplementedError("Serial transport I/O is not implemented yet.")

    def send(self, payload: bytes) -> None:
        raise NotImplementedError("Serial transport I/O is not implemented yet.")

    def request_sequence(
        self,
        payloads: list[bytes],
        *,
        timeout_ms: int | None = None,
        response_timeouts_ms: list[int] | None = None,
        frame_gap_timeout_ms: int | None = None,
    ) -> list[bytes]:
        raise NotImplementedError("Serial transport I/O is not implemented yet.")


class TcpTransportSkeleton:
    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        raise NotImplementedError("TCP transport I/O is not implemented yet.")


def _load_serial_module() -> Any:
    return importlib.import_module("serial")


def _serial_parity(parity: str) -> str:
    if parity == "none":
        return "N"
    if parity == "even":
        return "E"
    return "O"


def _recv_until_newline(sock: socket.socket) -> bytes:
    chunks = bytearray()
    while True:
        chunk = sock.recv(1024)
        if not chunk:
            break
        chunks.extend(chunk)
        if b"\n" in chunk:
            break
    if not chunks:
        raise TimeoutError("TCP transport read timed out.")
    return bytes(chunks)


def _read_serial_response(connection: Any, *, inter_byte_timeout_ms: int | None = None) -> bytes:
    if hasattr(connection, "read"):
        chunks = bytearray()
        first_chunk = connection.read(1)
        if not first_chunk:
            return b""
        chunks.extend(first_chunk)
        original_timeout = getattr(connection, "timeout", None) if inter_byte_timeout_ms is not None else None
        while True:
            if inter_byte_timeout_ms is not None:
                in_waiting = getattr(connection, "in_waiting", 0)
                if callable(in_waiting):
                    in_waiting = in_waiting()
                if isinstance(in_waiting, int) and in_waiting > 0:
                    chunk = connection.read(in_waiting)
                    if not chunk:
                        break
                    chunks.extend(chunk)
                    continue
                try:
                    if hasattr(connection, "timeout"):
                        connection.timeout = inter_byte_timeout_ms / 1000
                    chunk = connection.read(1)
                finally:
                    if hasattr(connection, "timeout") and original_timeout is not None:
                        connection.timeout = original_timeout
                if not chunk:
                    break
                chunks.extend(chunk)
                continue
            if chunks.endswith(b"\n"):
                break
            in_waiting = getattr(connection, "in_waiting", 0)
            if callable(in_waiting):
                in_waiting = in_waiting()
            if isinstance(in_waiting, int) and in_waiting > 0:
                chunk = connection.read(in_waiting)
                if not chunk:
                    break
                chunks.extend(chunk)
                continue
            chunk = connection.read(1)
            if not chunk:
                break
            chunks.extend(chunk)
        return bytes(chunks)
    if hasattr(connection, "read_until"):
        return connection.read_until(b"\n")
    raise OSError("Serial connection does not support read operations.")
