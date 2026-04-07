from __future__ import annotations

import os
import select
import struct
import time
from dataclasses import dataclass
from typing import Callable

from app.hardware.transport_config import EndpointTimeoutSettings, LinuxInputTransportSettings


@dataclass(frozen=True, slots=True)
class _InputEvent:
    event_type: int
    code: int
    value: int


class LinuxInputEventTransport:
    _PING_REQUEST = b"PING\n"
    _READ_REQUEST = b"READ\n"
    _CLEAR_REQUEST = b"CLEAR\n"

    _PONG_RESPONSE = b"PONG\n"
    _NO_CARD_RESPONSE = b"NO_CARD\n"
    _CLEARED_RESPONSE = b"CLEARED\n"
    _MALFORMED_RESPONSE = b"MALFORMED\n"

    _EV_KEY = 0x01
    _EV_SYN = 0x00
    _KEY_ENTER = 28
    _IGNORED_KEY_CODES = frozenset({29, 42, 54, 56, 97, 100, 125, 126})
    _KEYMAP = {
        2: "1",
        3: "2",
        4: "3",
        5: "4",
        6: "5",
        7: "6",
        8: "7",
        9: "8",
        10: "9",
        11: "0",
        16: "Q",
        17: "W",
        18: "E",
        19: "R",
        20: "T",
        21: "Y",
        22: "U",
        23: "I",
        24: "O",
        25: "P",
        30: "A",
        31: "S",
        32: "D",
        33: "F",
        34: "G",
        35: "H",
        36: "J",
        37: "K",
        38: "L",
        44: "Z",
        45: "X",
        46: "C",
        47: "V",
        48: "B",
        49: "N",
        50: "M",
        71: "7",
        72: "8",
        73: "9",
        75: "4",
        76: "5",
        77: "6",
        79: "1",
        80: "2",
        81: "3",
        82: "0",
    }
    _EVENT_STRUCTS = (
        struct.Struct("<qqHHi"),
        struct.Struct("<llHHi"),
    )

    def __init__(
        self,
        *,
        settings: LinuxInputTransportSettings,
        timeouts: EndpointTimeoutSettings,
        device_opener: Callable[[str, bool], "_InputDevice"] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._timeouts = timeouts
        self._device_opener = device_opener or _open_input_device
        self._monotonic = monotonic or time.monotonic

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        if payload == self._PING_REQUEST:
            with self._device_opener(self._settings.device_path, True):
                return self._PONG_RESPONSE
        if payload == self._READ_REQUEST:
            return self._read_card(timeout_ms=timeout_ms)
        if payload == self._CLEAR_REQUEST:
            self._clear_pending_events()
            return self._CLEARED_RESPONSE
        raise NotImplementedError(f"Unsupported RFID HID request payload: {payload!r}")

    def _read_card(self, *, timeout_ms: int | None) -> bytes:
        timeout_seconds = (timeout_ms if timeout_ms is not None else self._timeouts.read_timeout_ms) / 1000
        deadline = self._monotonic() + timeout_seconds
        chars: list[str] = []
        buffer = bytearray()
        saw_activity = False

        with self._device_opener(self._settings.device_path, True) as device:
            while True:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    if chars:
                        raise TimeoutError("RFID HID input read timed out before end-of-card marker.")
                    if buffer:
                        return self._MALFORMED_RESPONSE
                    return self._NO_CARD_RESPONSE
                if not device.wait_until_readable(remaining):
                    if chars:
                        raise TimeoutError("RFID HID input read timed out before end-of-card marker.")
                    if buffer:
                        return self._MALFORMED_RESPONSE
                    return self._NO_CARD_RESPONSE
                chunk = device.read()
                if not chunk:
                    if saw_activity or chars or buffer:
                        return self._MALFORMED_RESPONSE
                    return self._NO_CARD_RESPONSE
                saw_activity = True
                buffer.extend(chunk)
                while True:
                    decoded = self._decode_event(buffer)
                    if decoded is None:
                        break
                    event, consumed = decoded
                    del buffer[:consumed]
                    if event.event_type == self._EV_SYN:
                        continue
                    if event.event_type != self._EV_KEY or event.value != 1:
                        continue
                    if event.code in self._IGNORED_KEY_CODES:
                        continue
                    if event.code == self._KEY_ENTER:
                        if chars:
                            return f"UID:{''.join(chars)}\n".encode("ascii")
                        continue
                    character = self._KEYMAP.get(event.code)
                    if character is None:
                        return self._MALFORMED_RESPONSE
                    chars.append(character)

    def _clear_pending_events(self) -> None:
        with self._device_opener(self._settings.device_path, True) as device:
            while device.wait_until_readable(0):
                if not device.read():
                    break

    @classmethod
    def _decode_event(cls, buffer: bytearray) -> tuple[_InputEvent, int] | None:
        for event_struct in cls._EVENT_STRUCTS:
            if len(buffer) < event_struct.size:
                continue
            raw_event = bytes(buffer[: event_struct.size])
            _, _, event_type, code, value = event_struct.unpack(raw_event)
            if event_type not in (cls._EV_SYN, cls._EV_KEY):
                continue
            if value not in (0, 1, 2):
                continue
            return _InputEvent(event_type=event_type, code=code, value=value), event_struct.size
        return None


class _InputDevice:
    def __init__(self, fd: int) -> None:
        self._fd = fd

    def read(self) -> bytes:
        return os.read(self._fd, 4096)

    def wait_until_readable(self, timeout_seconds: float) -> bool:
        readable, _, _ = select.select([self._fd], [], [], timeout_seconds)
        return bool(readable)

    def close(self) -> None:
        os.close(self._fd)

    def __enter__(self) -> "_InputDevice":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _open_input_device(device_path: str, nonblocking: bool) -> _InputDevice:
    flags = os.O_RDONLY
    if nonblocking:
        flags |= os.O_NONBLOCK
    return _InputDevice(os.open(device_path, flags))
