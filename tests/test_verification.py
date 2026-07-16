from vantadsp import protocol
from vantadsp.verification import verify_eq_readback


def test_verifies_legacy_parametric_readback():
    gains = [5.0, 3.0, -2.5, -3.0, -2.0, -0.5, 1.0]
    request = protocol.set_parametric_eq(protocol.EQ_CATEGORIES["custom_c2"], protocol.charge6_bands(gains))
    payload = protocol.LegacyFrame.decode(request, force_long=True).payload
    response = protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, payload, long_length=True).encode()
    result = verify_eq_readback(gains, [response])
    assert result.verified
    assert result.actual == gains
    assert result.deltas == [0.0] * 7


def test_reports_readback_mismatch_by_band():
    expected = [5.0, 3.0, -2.5, -3.0, -2.0, -0.5, 1.0]
    actual = [5.0, 3.0, -2.5, -3.0, -2.0, -0.5, 0.5]
    request = protocol.set_parametric_eq(protocol.EQ_CATEGORIES["custom_c2"], protocol.charge6_bands(actual))
    payload = protocol.LegacyFrame.decode(request, force_long=True).payload
    response = protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, payload, long_length=True).encode()
    result = verify_eq_readback(expected, [response])
    assert result.status == "mismatch"
    assert result.deltas == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.5]


def test_verifies_legacy_simple_readback():
    payload = bytes.fromhex("02 C1 C1 03 01 02 02 FF 03 06")
    response = protocol.LegacyFrame(protocol.RET_SIMPLE_EQ, payload).encode()
    result = verify_eq_readback([2, -1, 6], [response])
    assert result.verified
    assert result.source == "legacy-simple/0x6D"


def test_verifies_legacy_level_readback():
    payload = bytes.fromhex("C1 C1 06 03 01 02 02 FF 03 06")
    response = protocol.LegacyFrame(protocol.RET_ADVANCED_EQ, payload, long_length=True).encode()
    result = verify_eq_readback([2, -1, 6], [response])
    assert result.verified
    assert result.source == "legacy-levels/0x99"


def test_verifies_protocol4_parametric_readback():
    gains = [1.0, 0.5, 0.0, -0.5, -1.0, 2.0, 3.0]
    bands = [protocol.ParametricBand(1, gain, 125.0 * (2**index), 0.7) for index, gain in enumerate(gains)]
    value = protocol.p4_parametric_payload(protocol.EQ_CATEGORIES["custom_c2"], bands)
    feature = protocol.P4_FEATURE_EQ_INFO.to_bytes(2, "little") + len(value).to_bytes(2, "little") + value
    response = protocol.p4_frame(0x0002, feature)
    result = verify_eq_readback(gains, [response])
    assert result.verified
    assert result.source == "protocol4/0E02"


def test_verifies_protocol4_grip_quantized_readback():
    gains = [6.0, 5.5, 5.0, 4.5, 4.0, 3.5, 3.0]
    value = protocol.p4_grip_custom_payload(protocol.EQ_CATEGORIES["custom_c2"], gains)
    feature = protocol.P4_FEATURE_SET_EQ.to_bytes(2, "little") + len(value).to_bytes(2, "little") + value
    result = verify_eq_readback(gains, [protocol.p4_frame(0x0002, feature)])
    assert result.verified
    assert result.source == "protocol4-grip/0E7F"


def test_reports_unverified_when_readback_is_missing():
    result = verify_eq_readback([0, 0, 0], [])
    assert result.status == "unverified"
    assert result.actual is None
