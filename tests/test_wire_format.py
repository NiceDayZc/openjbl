"""Byte-exact tests for what actually reaches the speaker.

Everything here pins bytes rather than shape. The audit found that the EQ
category, the extended encoder's frequency/Q table and the apply gate could all
be mutated with the whole suite green, because the tests asserted that a list was
non-empty and that a fake echoed itself back. These are the assertions that fail
when the wire changes.

The Charge 6 vectors come from docs/DEVICE_CHARGE6_20E3.md, which records a real
write/read-back cycle against the hardware.
"""

import struct

import pytest

from openjbl import protocol
from openjbl.models import auto_eq_frames
from openjbl.protocol import EQ_CATEGORIES, LegacyFrame, custom_c2_shape

CHARGE6 = "20e3"
BOOMBOX4 = "214e"  # PROTOCOL_4, 7-band parametric


def test_custom_c2_band_table_matches_the_shipped_asset():
    """The table is read from custom_c2_eq.json; restating it in Python is how the
    shelves drifted to Q=0.7 and shipped a slope the app never sends."""
    assert custom_c2_shape() == (
        (0, 125.0, 0.707),
        (1, 250.0, 2.0),
        (1, 500.0, 2.0),
        (1, 1000.0, 2.0),
        (1, 2000.0, 2.0),
        (1, 4000.0, 2.0),
        (2, 8000.0, 0.707),
    )


def test_the_extended_encoder_uses_the_same_band_table_as_the_standard_one():
    """The +/-24 dB path is the highest-energy write the product emits; it must not
    reach hardware with a different filter shape than the audited one."""
    standard = protocol.charge6_bands([0] * 7)
    extended = protocol.charge6_extended_bands([0] * 7)
    for left, right in zip(standard, extended, strict=True):
        assert (left.filter_type, left.frequency, left.q) == (right.filter_type, right.frequency, right.q)


def _decode_parametric(frame: bytes) -> dict:
    decoded = LegacyFrame.decode(frame, force_long=True)
    assert decoded.command == protocol.SET_ADVANCED_EQ
    return protocol.parse_parametric_eq(decoded.payload)


def test_charge6_write_frame_is_byte_exact():
    """A golden vector: the frame for a known curve, byte for byte."""
    path, frames = auto_eq_frames(CHARGE6, [0, 0, 0, 0, 0, 0, 0])
    assert path == "legacy-parametric/0x97"
    assert len(frames) == 1
    frame = frames[0]

    assert frame[0] == protocol.IDENTIFIER
    assert frame[1] == protocol.SET_ADVANCED_EQ
    assert int.from_bytes(frame[2:4], "big") == len(frame) - 4, "long-form length header"
    # category twice, then band count, then the sample rate -- SetAdvancedNewEQCommand's layout
    assert frame[4] == EQ_CATEGORIES["custom_c2"] == 0xC2
    assert frame[5] == EQ_CATEGORIES["custom_c2"]
    assert frame[6] == 7
    assert struct.unpack(">I", frame[7:11])[0] == 48000
    # then 13 bytes per band: type, gain f32, frequency f32, q f32
    assert len(frame) == 11 + 7 * 13
    # Band 1: low shelf, 0 dB, 125 Hz, Q 0.707. Compared as the float32 the wire
    # actually carries -- 0.707 has no exact 32-bit representation.
    assert frame[11] == 0
    assert frame[12:24] == struct.pack(">fff", 0.0, 125.0, 0.707)


def test_the_eq_category_byte_is_pinned():
    """Writing to the wrong category silently edits a preset the user never chose.
    Nothing else in the suite fails if this constant changes."""
    assert EQ_CATEGORIES["custom_c2"] == 0xC2
    assert EQ_CATEGORIES["custom"] == 0xC1
    _, frames = auto_eq_frames(CHARGE6, [0] * 7)
    assert _decode_parametric(frames[0])["category"] == 0xC2


def test_protocol4_write_frame_is_byte_exact():
    """The Protocol 4 path has its own category mapping and its own field order
    (type, frequency, gain, q -- the legacy one is type, gain, frequency, q).
    Neither was pinned by anything."""
    path, frames = auto_eq_frames(BOOMBOX4, [0] * 7)
    assert path == "protocol4-parametric/0E02"
    assert len(frames) == 1
    frame = frames[0]

    header, command, count, index, size = struct.unpack("<HHBBH", frame[:8])
    assert header == 0xDD00 and command == protocol.P4_SET_DEVICE_INFO
    assert (count, index) == (1, 0)
    assert size == len(frame) - 8
    feature, length = struct.unpack("<HH", frame[8:12])
    assert feature == protocol.P4_FEATURE_EQ_INFO == 0x0E02
    payload = frame[12 : 12 + length]
    # Both custom categories collapse to 0xC1 on Protocol 4, so this is pinned as
    # a literal rather than by asking the map what the map says.
    assert payload[0] == 0xC1
    assert payload[1] == 1 and payload[2] == 7
    assert struct.unpack(">IIII", payload[3:19]) == (0, 48000, 0, 0)
    band1 = payload[19:32]
    assert band1[0] == 0, "low shelf"
    frequency, gain, q = struct.unpack(">fff", band1[1:13])
    assert (frequency, gain) == (125.0, 0.0), "Protocol 4 puts frequency before gain"
    assert q == pytest.approx(0.707), "the shelf Q comes from the shipped asset here too"


def test_protocol4_and_legacy_disagree_about_field_order_on_purpose():
    """If these ever match, one of the two encoders is wrong."""
    band = protocol.ParametricBand(1, gain=3.0, frequency=1000.0, q=2.0)
    assert band.encode_legacy() == bytes((1,)) + struct.pack(">fff", 3.0, 1000.0, 2.0)
    assert band.encode_protocol4() == bytes((1,)) + struct.pack(">fff", 1000.0, 3.0, 2.0)
    assert band.encode_legacy() != band.encode_protocol4()


@pytest.mark.parametrize("gain", [6.0, -9.0, 0.5])
def test_standard_charge6_gains_survive_the_round_trip(gain):
    gains = [gain] + [0.0] * 6 if gain == -9.0 else [gain] * 7
    _, frames = auto_eq_frames(CHARGE6, gains)
    bands = _decode_parametric(frames[0])["bands"]
    assert [band["gain"] for band in bands] == pytest.approx(gains)


def test_extended_write_carries_the_full_range_and_the_asset_q():
    _, frames = auto_eq_frames(CHARGE6, [24, -24, 0, 0, 0, 0, 0], allow_extended=True)
    parsed = _decode_parametric(frames[0])
    assert parsed["category"] == 0xC2
    assert parsed["sample_rate"] == 48000
    gains = [band["gain"] for band in parsed["bands"]]
    assert gains == pytest.approx([24, -24, 0, 0, 0, 0, 0])
    assert parsed["bands"][0]["q"] == pytest.approx(0.707)
    assert parsed["bands"][0]["frequency"] == pytest.approx(125.0)


def test_read_frame_is_byte_exact():
    assert protocol.request_advanced_eq() == bytes.fromhex("AA 98 00 00")
    assert protocol.request_firmware_version() == bytes.fromhex("AA 41 00")
    assert protocol.request_eq_mode() == bytes.fromhex("AA 61 00")


def test_hardware_confirmed_charge6_curve_round_trips():
    """The exact curve docs/DEVICE_CHARGE6_20E3.md recorded reading off the device.

    Band 1 is -0.75 (a 0.75 dB negative step), the rest are 0.5 dB steps.
    """
    gains = [-0.75, -1, -1, 3, 4, 2, 0]
    _, frames = auto_eq_frames(CHARGE6, gains)
    parsed = _decode_parametric(frames[0])
    assert [band["gain"] for band in parsed["bands"]] == pytest.approx(gains)
    assert [band["frequency"] for band in parsed["bands"]] == [125, 250, 500, 1000, 2000, 4000, 8000]
    assert [band["filter_type"] for band in parsed["bands"]] == [0, 1, 1, 1, 1, 1, 2]
