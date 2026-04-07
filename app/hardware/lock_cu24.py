from __future__ import annotations

from dataclasses import dataclass


CU24_STX = 0x02
CU24_ETX = 0x03
CU24_ACK_SUCCESS = 0x10
CU24_CMD_GET_STATUS = 0x80
CU24_CMD_UNLOCK = 0x81
CU24_CMD_QUERY_VERSION = 0x8F
CU24_MIN_LOCK_NUMBER = 1
CU24_MAX_LOCK_NUMBER = 24


@dataclass(frozen=True, slots=True)
class Cu24Packet:
    address: int
    lock_number: int
    command: int
    ask: int
    data: bytes


def build_packet(*, address: int, lock_number: int, command: int, ask: int = 0x00, data: bytes = b"") -> bytes:
    _validate_byte(address, "address")
    _validate_byte(lock_number, "lock_number")
    _validate_byte(command, "command")
    _validate_byte(ask, "ask")
    if len(data) > 0xFF:
        raise ValueError("data is too long")
    body = bytes((CU24_STX, address, lock_number, command, ask, len(data), CU24_ETX))
    checksum = sum(body) & 0xFF
    return body + bytes((checksum,)) + data


def parse_packet(packet: bytes) -> Cu24Packet:
    if len(packet) < 8:
        raise ValueError("CU24 packet is too short")
    if packet[0] != CU24_STX:
        raise ValueError("CU24 packet STX mismatch")
    if packet[6] != CU24_ETX:
        raise ValueError("CU24 packet ETX mismatch")
    expected_checksum = sum(packet[:7]) & 0xFF
    if packet[7] != expected_checksum:
        raise ValueError("CU24 packet checksum mismatch")
    data_length = packet[5]
    data = packet[8:]
    if len(data) != data_length:
        raise ValueError("CU24 packet data length mismatch")
    return Cu24Packet(
        address=packet[1],
        lock_number=packet[2],
        command=packet[3],
        ask=packet[4],
        data=data,
    )


def protocol_lock_number(physical_lock_number: int) -> int:
    if not CU24_MIN_LOCK_NUMBER <= physical_lock_number <= CU24_MAX_LOCK_NUMBER:
        raise ValueError(f"physical lock number must be between {CU24_MIN_LOCK_NUMBER} and {CU24_MAX_LOCK_NUMBER}")
    return physical_lock_number - 1


def _validate_byte(value: int, name: str) -> None:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must fit in one byte")
