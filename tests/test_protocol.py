import math

import pytest

from vantadsp import protocol
from vantadsp.models import auto_eq_frames, find_models
from vantadsp.protocol import (
    EQ_CATEGORIES,
    LegacyFrame,
    LegacyStreamDecoder,
    ParametricBand,
    charge6_bands,
    p4_grip_custom_payload,
    p4_request_eq,
    p4_set_parametric_eq,
    parse_parametric_eq,
    parse_simple_eq,
    request_advanced_eq,
    request_eq_mode,
    request_firmware_version,
    request_simple_eq,
    set_parametric_eq,
    set_simple_eq,
)


def test_known_request_vectors():
    assert request_eq_mode() == bytes.fromhex("AA 61 00")
    assert request_firmware_version() == bytes.fromhex("AA 41 00")
    assert request_simple_eq() == bytes.fromhex("AA 6C 01 00")
    assert request_advanced_eq() == bytes.fromhex("AA 98 00 00")
    assert LegacyFrame.decode(request_advanced_eq()).command == 0x98


def test_simple_set_and_parse():
    assert set_simple_eq(0xC1, 2, -1, 6) == bytes.fromhex("AA 6E 08 C1 03 01 02 02 FF 03 06")
    parsed = parse_simple_eq(bytes.fromhex("02 C1 C1 03 01 02 02 FF 03 06"))
    assert parsed["active_category"] == 0xC1
    assert parsed["categories"][0]["parameters"] == {"bass": 2, "mid": -1, "treble": 6}


def test_stream_decoder_reassembles():
    decoder = LegacyStreamDecoder()
    assert decoder.feed(bytes.fromhex("00 AA 62")) == []
    frames = decoder.feed(bytes.fromhex("01 01"))
    assert frames == [LegacyFrame(0x62, b"\x01")]


def test_parametric_wire_layout_roundtrip_payload():
    bands = [ParametricBand(1, 2.5, 1000.0, 0.707)]
    raw = set_parametric_eq(EQ_CATEGORIES["custom_c2"], bands)
    frame = LegacyFrame.decode(raw, force_long=True)
    assert frame.payload[:3] == bytes((0xC2, 0xC2, 1))
    parsed = parse_parametric_eq(frame.payload)
    assert parsed["sample_rate"] == 48000
    assert math.isclose(parsed["bands"][0]["gain"], 2.5)
    assert math.isclose(parsed["bands"][0]["frequency"], 1000.0)


def test_protocol4_query_vector():
    assert p4_request_eq()[0] == bytes.fromhex("00 DD 02 00 01 00 05 00 01 0E 01 00 FF")


def test_protocol4_requires_seven_bands():
    with pytest.raises(ValueError):
        p4_set_parametric_eq(0xC2, [ParametricBand(1, 0, 1000, 0.707)])


def test_protocol4_parametric_payload_roundtrip():
    bands = [ParametricBand(1, float(index), 125.0 * (2**index), 0.7) for index in range(7)]
    payload = protocol.p4_parametric_payload(EQ_CATEGORIES["custom_c2"], bands)
    parsed = parse_parametric_eq(payload, protocol4_layout=True)
    assert parsed["sample_rate"] == 48000
    assert [band["gain"] for band in parsed["bands"]] == [float(index) for index in range(7)]


def test_model_database_and_recommendation():
    flip6 = find_models("204f")[0]
    assert flip6["name"] == "JBL Flip 6"
    assert flip6["transport"] == "PROTOCOL_GATT_BR_EDR"
    grip = find_models("2132")[0]
    assert grip["eq_path"] == "protocol4-grip-quantized"


def test_charge6_profile_limits():
    bands = charge6_bands([5, 3, -2.5, -3, -2, -0.5, 1])
    assert [band.frequency for band in bands] == [125, 250, 500, 1000, 2000, 4000, 8000]
    with pytest.raises(ValueError):
        charge6_bands([-0.5, 0, 0, 0, 0, 0, 0])
    with pytest.raises(ValueError):
        charge6_bands([0, 6.5, 0, 0, 0, 0, 0])


def test_grip_quantized_payload():
    payload = p4_grip_custom_payload(0xC2, [6, 0, -0.5, -1, -2, -3, -6])
    assert payload == bytes((0xC1, 0, 12, 13, 14, 16, 18, 24))


def test_auto_eq_charge6_selects_legacy_parametric():
    path, frames = auto_eq_frames("20e3", [0, 0, 0, 0, 0, 0, 0])
    assert path == "legacy-parametric/0x97"
    assert frames[0][:2] == bytes((0xAA, 0x97))


def test_auto_eq_grip_selects_protocol4_0e7f():
    path, frames = auto_eq_frames("2132", [0, 0, 0, 0, 0, 0, 0])
    assert path == "protocol4-grip-quantized/0E7F"
    assert frames[0][:4] == bytes((0x00, 0xDD, 0x02, 0x00))


def test_auto_eq_balance_selects_three_band():
    path, frames = auto_eq_frames("1f53", [1, 0, -1])
    assert path == "legacy-simple/0x6E"
    assert frames[0][:3] == bytes((0xAA, 0x6E, 8))
