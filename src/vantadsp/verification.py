"""Model-aware EQ read-back verification."""

from __future__ import annotations

import math
import struct
from dataclasses import asdict, dataclass

from . import protocol


@dataclass(frozen=True)
class EqVerification:
    status: str
    source: str
    expected: list[float]
    actual: list[float] | None
    deltas: list[float] | None
    message: str

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _comparison(expected: list[float], actual: list[float], source: str) -> EqVerification:
    if len(expected) != len(actual):
        return EqVerification(
            "mismatch",
            source,
            expected,
            actual,
            None,
            f"band count differs: requested {len(expected)}, read back {len(actual)}",
        )
    deltas = [round(got - want, 6) for want, got in zip(expected, actual, strict=True)]
    verified = all(
        math.isclose(want, got, rel_tol=0.0, abs_tol=1e-4) for want, got in zip(expected, actual, strict=True)
    )
    return EqVerification(
        "verified" if verified else "mismatch",
        source,
        expected,
        actual,
        deltas,
        "all read-back gains match the requested values" if verified else "one or more read-back gains differ",
    )


def _legacy_parametric_or_levels(payload: bytes) -> tuple[list[float], str] | None:
    try:
        decoded = protocol.parse_parametric_eq(payload)
        return [float(band["gain"]) for band in decoded["bands"]], "legacy-parametric/0x99"
    except ValueError:
        pass
    if len(payload) < 4:
        return None
    active = payload[0]
    offset = 1
    while offset + 3 <= len(payload):
        category, _scope, count = payload[offset : offset + 3]
        offset += 3
        end = offset + count * 2
        if end > len(payload):
            return None
        values = [float(struct.unpack("b", payload[index + 1 : index + 2])[0]) for index in range(offset, end, 2)]
        if category == active:
            return values, "legacy-levels/0x99"
        offset = end
    return None


def _legacy_gains(replies: list[bytes]) -> tuple[list[float], str] | None:
    for raw in replies:
        if not raw.startswith(b"\xaa"):
            continue
        try:
            frame = protocol.LegacyFrame.decode(raw)
        except ValueError:
            continue
        if frame.command == protocol.RET_SIMPLE_EQ:
            decoded = protocol.parse_simple_eq(frame.payload)
            active = decoded["active_category"]
            for category in decoded["categories"]:
                if category["category"] == active:
                    params = category["parameters"]
                    if all(name in params for name in ("bass", "mid", "treble")):
                        return [float(params[name]) for name in ("bass", "mid", "treble")], "legacy-simple/0x6D"
        if frame.command == protocol.RET_ADVANCED_EQ:
            result = _legacy_parametric_or_levels(frame.payload)
            if result is not None:
                return result
    return None


def _p4_feature_values(replies: list[bytes]) -> list[tuple[int, bytes]]:
    packets: dict[tuple[int, int], dict[int, bytes]] = {}
    for raw in replies:
        if not raw.startswith((b"\x00\xdd", b"\x01\xdd")) or len(raw) < 8:
            continue
        _header, command, count, index, size = struct.unpack("<HHBBH", raw[:8])
        if len(raw) < 8 + size or not count or index >= count:
            continue
        packets.setdefault((command, count), {})[index] = raw[8 : 8 + size]
    features: list[tuple[int, bytes]] = []
    for (_command, count), chunks in packets.items():
        if len(chunks) != count:
            continue
        payload = b"".join(chunks[index] for index in range(count))
        offset = 0
        while offset + 4 <= len(payload):
            feature, size = struct.unpack("<HH", payload[offset : offset + 4])
            offset += 4
            if offset + size > len(payload):
                break
            features.append((feature, payload[offset : offset + size]))
            offset += size
    return features


def _grip_gains(value: bytes) -> list[float] | None:
    if len(value) < 8:
        return None
    normal = [6.0 - 0.5 * index for index in range(25)]
    first = [6.0 - 0.5 * index for index in range(13)] + [-0.75 * index for index in range(1, 13)]
    tables = [first, *([normal] * 6)]
    indices = value[1:8]
    if any(index >= len(table) for index, table in zip(indices, tables, strict=True)):
        return None
    return [table[index] for index, table in zip(indices, tables, strict=True)]


def _protocol4_gains(replies: list[bytes]) -> tuple[list[float], str] | None:
    for feature, value in _p4_feature_values(replies):
        if feature == protocol.P4_FEATURE_EQ_INFO:
            try:
                decoded = protocol.parse_parametric_eq(value, protocol4_layout=True)
            except ValueError:
                continue
            return [float(band["gain"]) for band in decoded["bands"]], "protocol4/0E02"
        if feature == protocol.P4_FEATURE_SET_EQ:
            gains = _grip_gains(value)
            if gains is not None:
                return gains, "protocol4-grip/0E7F"
    return None


def verify_eq_readback(expected_gains: list[float], replies: list[bytes]) -> EqVerification:
    """Compare a model-specific EQ read response with requested gains."""
    expected = [float(value) for value in expected_gains]
    extracted = _legacy_gains(replies) or _protocol4_gains(replies)
    if extracted is None:
        return EqVerification(
            "unverified",
            "none",
            expected,
            None,
            None,
            "no supported EQ state could be decoded from the read-back response",
        )
    actual, source = extracted
    return _comparison(expected, actual, source)
