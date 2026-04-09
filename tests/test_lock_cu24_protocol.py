from __future__ import annotations

import pytest

from app.hardware.lock_cu24 import build_packet, parse_packet, protocol_lock_number


def test_cu24_packet_building_matches_verified_examples() -> None:
    assert build_packet(address=0, lock_number=0, command=0x80) == bytes.fromhex("02 00 00 80 00 00 03 85")
    assert build_packet(address=0, lock_number=0, command=0x8F) == bytes.fromhex("02 00 00 8F 00 00 03 94")
    assert build_packet(address=0, lock_number=0, command=0x81) == bytes.fromhex("02 00 00 81 00 00 03 86")
    assert build_packet(address=0, lock_number=1, command=0x81) == bytes.fromhex("02 00 01 81 00 00 03 87")


def test_cu24_packet_parsing_matches_verified_examples() -> None:
    packet = parse_packet(bytes.fromhex("02 00 01 81 10 00 03 97"))

    assert packet.address == 0
    assert packet.lock_number == 1
    assert packet.command == 0x81
    assert packet.ask == 0x10
    assert packet.data == b""


def test_cu24_packet_parsing_accepts_live_version_response_with_trailing_data() -> None:
    packet = parse_packet(bytes.fromhex("02 00 00 8F 10 02 03 BA 13 01"))

    assert packet.address == 0
    assert packet.lock_number == 0
    assert packet.command == 0x8F
    assert packet.ask == 0x10
    assert packet.data == bytes.fromhex("13 01")


def test_cu24_packet_checksum_validation_fails_on_invalid_checksum() -> None:
    with pytest.raises(ValueError, match="checksum mismatch"):
        parse_packet(bytes.fromhex("02 00 01 81 10 00 03 00"))


def test_cu24_packet_checksum_validation_uses_trailing_data_bytes() -> None:
    with pytest.raises(ValueError, match="checksum mismatch"):
        parse_packet(bytes.fromhex("02 00 00 8F 10 02 03 BA 13 00"))


def test_cu24_lock_number_translation_is_one_based_in_domain() -> None:
    assert protocol_lock_number(1) == 0
    assert protocol_lock_number(2) == 1
    with pytest.raises(ValueError, match="between 1 and 24"):
        protocol_lock_number(0)
