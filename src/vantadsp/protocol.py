"""Packet codecs recovered from JBL Portable 6.9.12.

All integer fields are unsigned on the wire. Java/Kotlin byte constants that
appear negative in JADX are represented here as their 0..255 equivalents.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

IDENTIFIER = 0xAA

REQ_EQ_MODE = 0x61
RET_EQ_MODE = 0x62
SET_EQ_MODE = 0x63
NOTIFY_EQ_CHANGE = 0x64
REQ_SIMPLE_EQ = 0x6C
RET_SIMPLE_EQ = 0x6D
SET_SIMPLE_EQ = 0x6E
REQ_ADVANCED_EQ = 0x98
RET_ADVANCED_EQ = 0x99
SET_ADVANCED_EQ = 0x97
REQ_FIRMWARE_VERSION = 0x41
RET_FIRMWARE_VERSION = 0x42

DEV_ACK = 0x00
# RET 0x99 is listed by PacketFormat.LONG_BYTES_COMMAND. The related request
# and set classes explicitly override data() with the same two-byte length.
LONG_LENGTH_COMMANDS = frozenset({SET_ADVANCED_EQ, REQ_ADVANCED_EQ, RET_ADVANCED_EQ, 0x92, 0x96})

EQ_CATEGORIES = {
    "balance": 0x00,
    "bass_boost_1": 0x01,
    "bass_boost_2": 0x02,
    "vocal": 0x03,
    "metal": 0x04,
    "classical": 0x05,
    "signature": 0x06,
    "relaxing": 0x07,
    "energetic": 0x08,
    "extreme": 0x09,
    "custom": 0xC1,
    "custom_c2": 0xC2,
}

P4_CATEGORY_MAP = {
    0x01: 0x50,
    0x03: 0x02,
    0x06: 0x80,
    0x07: 0x81,
    0x08: 0x82,
    0x09: 0x83,
    0x22: 0x85,
    0xC1: 0xC1,
    0xC2: 0xC1,
}

P4_FEATURE_EQ_INFO_QUERY = 0x0E01
P4_FEATURE_EQ_INFO = 0x0E02
P4_FEATURE_SET_EQ = 0x0E7F

FILTER_TYPES = {
    "low_shelf": 0,
    "peaking": 1,
    "high_shelf": 2,
    "low_pass": 3,
    "high_pass": 4,
}


def parse_hex(value: str) -> bytes:
    cleaned = value.replace("0x", "").replace(" ", "").replace(":", "").replace("-", "")
    if len(cleaned) % 2:
        raise ValueError("hex must contain a whole number of bytes")
    return bytes.fromhex(cleaned)


def hex_bytes(data: bytes) -> str:
    return data.hex(" ").upper()


@dataclass(frozen=True)
class LegacyFrame:
    command: int
    payload: bytes = b""
    long_length: bool = False

    def encode(self) -> bytes:
        if not 0 <= self.command <= 0xFF:
            raise ValueError("command must fit in one byte")
        if self.long_length or self.command in LONG_LENGTH_COMMANDS or len(self.payload) > 255:
            if len(self.payload) > 0xFFFF:
                raise ValueError("payload is too large")
            return bytes((IDENTIFIER, self.command)) + len(self.payload).to_bytes(2, "big") + self.payload
        return bytes((IDENTIFIER, self.command, len(self.payload))) + self.payload

    @classmethod
    def decode(cls, data: bytes, *, force_long: bool | None = None) -> LegacyFrame:
        if len(data) < 3 or data[0] != IDENTIFIER:
            raise ValueError("not an AA legacy frame")
        is_long = data[1] in LONG_LENGTH_COMMANDS if force_long is None else force_long
        header = 4 if is_long else 3
        if len(data) < header:
            raise ValueError("truncated header")
        size = int.from_bytes(data[2:4], "big") if is_long else data[2]
        if len(data) != header + size:
            raise ValueError(f"length mismatch: header says {size}, received {len(data) - header}")
        return cls(data[1], data[header:], is_long)


class LegacyStreamDecoder:
    """Reassemble legacy frames split across BLE notifications or serial reads."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[LegacyFrame]:
        self._buffer.extend(data)
        frames: list[LegacyFrame] = []
        while True:
            try:
                start = self._buffer.index(IDENTIFIER)
            except ValueError:
                self._buffer.clear()
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < 3:
                break
            is_long = self._buffer[1] in LONG_LENGTH_COMMANDS
            header = 4 if is_long else 3
            if len(self._buffer) < header:
                break
            size = int.from_bytes(self._buffer[2:4], "big") if is_long else self._buffer[2]
            total = header + size
            if len(self._buffer) < total:
                break
            raw = bytes(self._buffer[:total])
            del self._buffer[:total]
            frames.append(LegacyFrame.decode(raw, force_long=is_long))
        return frames


def request_eq_mode() -> bytes:
    return LegacyFrame(REQ_EQ_MODE).encode()


def request_firmware_version() -> bytes:
    return LegacyFrame(REQ_FIRMWARE_VERSION).encode()


def set_eq_mode(mode: int) -> bytes:
    if not 0 <= mode <= 255:
        raise ValueError("mode must be 0..255")
    return LegacyFrame(SET_EQ_MODE, bytes((mode,))).encode()


def request_simple_eq() -> bytes:
    return LegacyFrame(REQ_SIMPLE_EQ, b"\x00").encode()


def set_simple_eq(category: int, bass: int, mid: int, treble: int) -> bytes:
    values = (bass, mid, treble)
    if not 0 <= category <= 255:
        raise ValueError("category must be 0..255")
    if any(not -128 <= value <= 127 for value in values):
        raise ValueError("simple EQ wire values must be signed bytes (-128..127)")
    payload = bytes((category, 3, 1, bass & 0xFF, 2, mid & 0xFF, 3, treble & 0xFF))
    return LegacyFrame(SET_SIMPLE_EQ, payload).encode()


def parse_simple_eq(payload: bytes) -> dict:
    if len(payload) < 2:
        raise ValueError("simple EQ response is too short")
    scope, active = payload[0], payload[1]
    categories = []
    offset = 2
    while offset + 2 <= len(payload):
        category, count = payload[offset], payload[offset + 1]
        offset += 2
        params = {}
        for _ in range(count):
            if offset + 2 > len(payload):
                raise ValueError("truncated simple EQ parameter")
            kind, raw = payload[offset], payload[offset + 1]
            params[{1: "bass", 2: "mid", 3: "treble"}.get(kind, f"type_{kind}")] = struct.unpack("b", bytes((raw,)))[0]
            offset += 2
        categories.append({"category": category, "active": category == active, "parameters": params})
    return {"scope": scope, "active_category": active, "categories": categories}


def request_advanced_eq() -> bytes:
    return LegacyFrame(REQ_ADVANCED_EQ, b"", long_length=True).encode()


def set_advanced_levels(active_category: int, levels: Sequence[int], scope: int = 6) -> bytes:
    if not 1 <= len(levels) <= 7:
        raise ValueError("advanced level EQ requires 1..7 bands")
    if any(not -128 <= level <= 127 for level in levels):
        raise ValueError("each level must fit in a signed byte")
    body = bytes((EQ_CATEGORIES["custom"], scope, len(levels)))
    body += b"".join(bytes((index, level & 0xFF)) for index, level in enumerate(levels, 1))
    return LegacyFrame(SET_ADVANCED_EQ, bytes((active_category,)) + body, long_length=True).encode()


@dataclass(frozen=True)
class ParametricBand:
    filter_type: int
    gain: float
    frequency: float
    q: float

    def validate(self) -> None:
        if self.filter_type not in range(5):
            raise ValueError("filter_type must be 0..4")
        if not -24.0 <= self.gain <= 24.0:
            raise ValueError("gain outside conservative -24..24 dB bound")
        if not 10.0 <= self.frequency <= 40000.0:
            raise ValueError("frequency outside 10..40000 Hz bound")
        if not 0.05 <= self.q <= 30.0:
            raise ValueError("Q outside 0.05..30 bound")

    def encode_legacy(self) -> bytes:
        self.validate()
        return bytes((self.filter_type,)) + struct.pack(">fff", self.gain, self.frequency, self.q)

    def encode_protocol4(self) -> bytes:
        self.validate()
        # Protocol 4 changes the field order: type, frequency, gain, Q.
        return bytes((self.filter_type,)) + struct.pack(">fff", self.frequency, self.gain, self.q)


def set_parametric_eq(active_category: int, bands: Sequence[ParametricBand], sample_rate: int = 48000) -> bytes:
    if not 1 <= len(bands) <= 7:
        raise ValueError("parametric EQ requires 1..7 bands")
    if not 8000 <= sample_rate <= 384000:
        raise ValueError("implausible sample rate")
    # APK SetAdvancedNewEQCommand duplicates active_category at payload[0:2].
    payload = bytes((active_category, active_category, len(bands)))
    payload += struct.pack(">I", sample_rate)
    payload += b"".join(band.encode_legacy() for band in bands)
    return LegacyFrame(SET_ADVANCED_EQ, payload, long_length=True).encode()


def charge6_bands(gains: Sequence[float]) -> list[ParametricBand]:
    """Build the custom-EQ shape exposed by the Charge 6 UI.

    Band 1 uses 0.5 dB positive steps and 0.75 dB negative steps (-9..+6).
    Bands 2..7 use 0.5 dB steps (-6..+6). Frequency and Q are fixed to
    the custom C2 values shipped in charge6_preset_eq/custom_c2_eq.
    """
    if len(gains) != 7:
        raise ValueError("Charge 6 requires exactly 7 gains")
    first = float(gains[0])
    if not -9.0 <= first <= 6.0:
        raise ValueError("Charge 6 band 1 must be -9..+6 dB")
    first_step = 0.75 if first < 0 else 0.5
    if abs(first / first_step - round(first / first_step)) > 1e-6:
        raise ValueError(f"Charge 6 band 1 must use {first_step:g} dB steps at this sign")
    for value in gains[1:]:
        value = float(value)
        if not -6.0 <= value <= 6.0 or abs(value * 2 - round(value * 2)) > 1e-6:
            raise ValueError("Charge 6 bands 2..7 must be -6..+6 dB in 0.5 dB steps")
    frequencies = (125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0)
    kinds = (0, 1, 1, 1, 1, 1, 2)
    q_values = (0.7, 2.0, 2.0, 2.0, 2.0, 2.0, 0.7)
    return [
        ParametricBand(kind, float(gain), frequency, q)
        for kind, gain, frequency, q in zip(kinds, gains, frequencies, q_values, strict=True)
    ]


def parse_parametric_eq(payload: bytes, *, protocol4_layout: bool = False) -> dict:
    if len(payload) < 7:
        raise ValueError("parametric response is too short")
    active, category, count = payload[:3]
    if protocol4_layout:
        if len(payload) < 19:
            raise ValueError("Protocol 4 parametric response is too short")
        sample_rate = struct.unpack(">I", payload[7:11])[0]
        offset = 19
    else:
        sample_rate = struct.unpack(">I", payload[3:7])[0]
        offset = 7
    bands = []
    for _ in range(count):
        if offset + 13 > len(payload):
            raise ValueError("truncated parametric band")
        kind = payload[offset]
        a, b, q = struct.unpack(">fff", payload[offset + 1 : offset + 13])
        gain, frequency = (b, a) if protocol4_layout else (a, b)
        bands.append({"filter_type": kind, "gain": gain, "frequency": frequency, "q": q})
        offset += 13
    return {"active_category": active, "category": category, "sample_rate": sample_rate, "bands": bands}


def p4_frame(command_id: int, payload: bytes, *, forward: bool = False, index: int = 0, count: int = 1) -> bytes:
    if len(payload) > 490:
        raise ValueError("use p4_frames for payloads larger than 490 bytes")
    header = 0xDD01 if forward else 0xDD00
    return struct.pack("<HHBBH", header, command_id, count, index, len(payload)) + payload


def p4_frames(command_id: int, payload: bytes, *, forward: bool = False) -> list[bytes]:
    chunks = [payload[i : i + 490] for i in range(0, len(payload), 490)] or [b""]
    return [p4_frame(command_id, chunk, forward=forward, index=i, count=len(chunks)) for i, chunk in enumerate(chunks)]


def p4_get(features: Iterable[int]) -> list[bytes]:
    payload = b"".join(struct.pack("<H", feature) for feature in features)
    return p4_frames(0x0001, payload)


def p4_set(feature_values: Iterable[tuple[int, bytes]]) -> list[bytes]:
    payload = b"".join(struct.pack("<HH", feature, len(value)) + value for feature, value in feature_values)
    return p4_frames(0x0002, payload)


def p4_request_eq(category: int = 0xFF) -> list[bytes]:
    return p4_set(((P4_FEATURE_EQ_INFO_QUERY, bytes((category,))),))


def p4_parametric_payload(active_category: int, bands: Sequence[ParametricBand]) -> bytes:
    if len(bands) != 7:
        raise ValueError("APK Protocol 4 EQ path always emits exactly 7 bands")
    mapped = P4_CATEGORY_MAP.get(active_category)
    if mapped is None:
        raise ValueError(f"category 0x{active_category:02X} has no Protocol 4 mapping")
    # category, enabled, band count, four big-endian ints: 0, 48000, 0, 0
    prefix = bytes((mapped, 1, 7)) + struct.pack(">IIII", 0, 48000, 0, 0)
    return prefix + b"".join(band.encode_protocol4() for band in bands)


def p4_set_parametric_eq(active_category: int, bands: Sequence[ParametricBand]) -> list[bytes]:
    return p4_set(((P4_FEATURE_EQ_INFO, p4_parametric_payload(active_category, bands)),))


def p4_grip_custom_payload(active_category: int, gains: Sequence[float], raw_tail: bytes = b"") -> bytes:
    """Build the quantized 7-band payload used by Grip/GO 5/Essential SE.

    This is a direct port of PortableControl.getGripEQPayload. Values must
    exactly match a UI step because the firmware receives table indices.
    """
    if len(gains) != 7:
        raise ValueError("Grip-style EQ requires exactly 7 gains")
    mapped = P4_CATEGORY_MAP.get(active_category)
    if mapped not in (0xC1,):
        raise ValueError("quantized builder is for CUSTOM/CUSTOM_C2 categories")
    normal = [6.0 - 0.5 * index for index in range(25)]
    first = [6.0 - 0.5 * index for index in range(13)] + [-0.75 * index for index in range(1, 13)]
    indices = []
    for index, gain in enumerate(gains):
        table = first if index == 0 else normal
        try:
            indices.append(next(i for i, value in enumerate(table) if abs(value - float(gain)) < 1e-6))
        except StopIteration as exc:
            raise ValueError(f"gain {gain} is not a valid Grip-style step for band {index + 1}") from exc
    return bytes((mapped, *indices)) + raw_tail


def p4_set_grip_eq(active_category: int, gains: Sequence[float], raw_tail: bytes = b"") -> list[bytes]:
    return p4_set(((P4_FEATURE_SET_EQ, p4_grip_custom_payload(active_category, gains, raw_tail)),))


def describe_frame(raw: bytes) -> dict:
    if raw.startswith(b"\xaa"):
        frame = LegacyFrame.decode(raw)
        result = {"protocol": "legacy", "command": frame.command, "payload_hex": hex_bytes(frame.payload)}
        if frame.command == RET_EQ_MODE and frame.payload:
            result["eq_mode"] = frame.payload[0]
        elif frame.command == RET_FIRMWARE_VERSION:
            result["firmware_version"] = ".".join(str(value) for value in frame.payload)
        elif frame.command == RET_SIMPLE_EQ:
            result["simple_eq"] = parse_simple_eq(frame.payload)
        elif frame.command == RET_ADVANCED_EQ:
            try:
                result["parametric_eq"] = parse_parametric_eq(frame.payload)
            except ValueError:
                result["note"] = "advanced level/preset response; inspect payload_hex"
        return result
    if raw.startswith((b"\x00\xdd", b"\x01\xdd")) and len(raw) >= 8:
        header, command, count, index, size = struct.unpack("<HHBBH", raw[:8])
        return {
            "protocol": "protocol4",
            "forward": header == 0xDD01,
            "command": command,
            "packet_count": count,
            "packet_index": index,
            "payload_length": size,
            "payload_hex": hex_bytes(raw[8:]),
        }
    raise ValueError("unknown frame identifier")
