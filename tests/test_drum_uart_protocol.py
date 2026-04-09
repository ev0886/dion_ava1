from __future__ import annotations

import pytest

from app.hardware.drum_uart import build_long_packet, build_short_packet, parse_packet, validate_position


def test_drum_packet_building_matches_verified_examples() -> None:
    assert build_long_packet(0x12, 0) == bytes.fromhex("12 00 00 F7")
    assert build_long_packet(0x12, 5) == bytes.fromhex("12 00 05 F2")
    assert build_long_packet(0x11, 5) == bytes.fromhex("11 00 05 F1")
    assert build_short_packet(0x30) == bytes.fromhex("30 D5")


def test_drum_packet_parsing_matches_verified_examples() -> None:
    packet = parse_packet(bytes.fromhex("24 00 05 C4"))

    assert packet.command == 0x24
    assert packet.argument == 5


def test_drum_packet_crc_validation_fails_on_invalid_crc() -> None:
    with pytest.raises(ValueError, match="CRC mismatch"):
        parse_packet(bytes.fromhex("24 00 05 00"))


def test_drum_position_validation_enforces_0_to_31() -> None:
    assert validate_position(0) == 0
    assert validate_position(31) == 31
    with pytest.raises(ValueError, match="between 0 and 31"):
        validate_position(32)
