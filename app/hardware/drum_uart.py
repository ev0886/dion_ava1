from __future__ import annotations

from dataclasses import dataclass


DRUM_SETPOS = 0x11
DRUM_GETPOS = 0x12
DRUM_CONF_OK = 0x30
DRUM_ANS1_ACCEPTED = 0x21
DRUM_ANS1_BUSY = 0x22
DRUM_ANS1_UNKNOWN = 0x23
DRUM_ANS1_RESULT = 0x24
DRUM_ANS2_OK = 0x25
DRUM_ANS2_ERR = 0x26
DRUM_CRC_XOR = 0xE5
DRUM_MIN_POSITION = 0
DRUM_MAX_POSITION = 31


@dataclass(frozen=True, slots=True)
class DrumPacket:
    command: int
    argument: int | None = None


def build_long_packet(command: int, argument: int) -> bytes:
    if not 0 <= command <= 0xFF:
        raise ValueError("command must fit in one byte")
    if not 0 <= argument <= 0xFFFF:
        raise ValueError("argument must fit in uint16")
    body = bytes((command, (argument >> 8) & 0xFF, argument & 0xFF))
    return body + bytes((_crc_for(body),))


def build_short_packet(command: int) -> bytes:
    if not 0 <= command <= 0xFF:
        raise ValueError("command must fit in one byte")
    body = bytes((command,))
    return body + bytes((_crc_for(body),))


def parse_packet(packet: bytes) -> DrumPacket:
    if len(packet) == 4:
        body = packet[:3]
        expected_crc = _crc_for(body)
        if packet[3] != expected_crc:
            raise ValueError("drum packet CRC mismatch")
        return DrumPacket(command=packet[0], argument=(packet[1] << 8) | packet[2])
    if len(packet) == 2:
        body = packet[:1]
        expected_crc = _crc_for(body)
        if packet[1] != expected_crc:
            raise ValueError("drum packet CRC mismatch")
        return DrumPacket(command=packet[0], argument=None)
    raise ValueError("drum packet must be 2 or 4 bytes long")


def validate_position(position: int) -> int:
    if not DRUM_MIN_POSITION <= position <= DRUM_MAX_POSITION:
        raise ValueError(f"position must be between {DRUM_MIN_POSITION} and {DRUM_MAX_POSITION}")
    return position


def _crc_for(body: bytes) -> int:
    crc = DRUM_CRC_XOR
    for byte in body:
        crc ^= byte
    return crc
