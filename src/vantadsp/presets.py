"""Curated tonal profiles resolved safely against each model's EQ controls."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from .models import GRIP_STYLE_P4_PIDS, gain_count_for_pid, get_model, presets_for_pid

REFERENCE_FREQUENCIES = (125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0)


@dataclass(frozen=True)
class SoundProfile:
    key: str
    name: str
    description: str
    gains: tuple[float, float, float, float, float, float, float]
    tags: tuple[str, ...] = ()


PROFILES = (
    SoundProfile(
        "flat",
        "Flat / Reference",
        "No tonal shaping; use this as a level-checking baseline",
        (0, 0, 0, 0, 0, 0, 0),
        ("reference",),
    ),
    SoundProfile(
        "balanced",
        "Balanced",
        "Even, fatigue-free tuning with no strongly emphasized range",
        (1, 0.5, 0, 0, 0, 0.5, 1),
        ("daily",),
    ),
    SoundProfile(
        "bass",
        "Bass Heavy",
        "Strong 125-250 Hz weight with restrained mids to limit muddiness",
        (6, 4, 1, -1, -1, 0, 1),
        ("bass",),
    ),
    SoundProfile(
        "deep-bass",
        "Deep Bass",
        "Deeper low-end weight with reduced low-mids for additional space",
        (6, 3, 0, -2, -1, 0, 0.5),
        ("bass", "electronic"),
    ),
    SoundProfile(
        "punch",
        "Punch Bass",
        "Tight impact focused on kick and rhythm rather than bloom",
        (4, 5, 2, -1, -1, 0.5, 1),
        ("bass", "rock"),
    ),
    SoundProfile(
        "warm", "Warm", "Smooth and relaxed with reduced upper-range bite", (3, 2, 1, 0.5, 0, -0.5, -1), ("relaxed",)
    ),
    SoundProfile(
        "loudness",
        "Low-volume Loudness",
        "Lifts both extremes to compensate at low playback levels",
        (4, 2, 0, -1, 0, 1.5, 3),
        ("quiet",),
    ),
    SoundProfile(
        "clear",
        "Crystal Clear",
        "Reduces low-mid congestion and adds presence and air",
        (0, -1, -2, 0, 2, 3, 4),
        ("clarity",),
    ),
    SoundProfile(
        "bright",
        "Bright",
        "Open and prominent top end for dark-sounding sources",
        (-0.75, -0.5, -1, 0, 2, 4, 5),
        ("treble",),
    ),
    SoundProfile(
        "detail",
        "Detail Monitor",
        "Analytical tuning with reduced excess bass and moderate upper-mid lift",
        (-1.5, -1, -1, 1, 2, 2.5, 2),
        ("monitor",),
    ),
    SoundProfile(
        "vocal",
        "Vocal Focus",
        "Brings vocals and dialogue forward while reducing masking bass",
        (-0.75, -1, -1, 3, 4, 2, 0),
        ("voice",),
    ),
    SoundProfile(
        "podcast",
        "Podcast / Speech",
        "Prioritizes speech intelligibility and reduces rumble",
        (-3, -2, -1, 3, 4, 2, -1),
        ("voice",),
    ),
    SoundProfile(
        "acoustic",
        "Acoustic",
        "Preserves instrument body while adding upper detail",
        (1, 1, 0.5, 1, 1.5, 2, 2),
        ("music",),
    ),
    SoundProfile(
        "rock",
        "Rock",
        "Clear kick and guitars with impact and an open top end",
        (4, 3, -1, 1, 3, 3, 2),
        ("music", "rock"),
    ),
    SoundProfile(
        "metal",
        "Metal",
        "Controls low-mid guitar overlap and emphasizes attack",
        (3, 1, -2, 0, 3, 4, 2),
        ("music", "metal"),
    ),
    SoundProfile(
        "hip-hop",
        "Hip-Hop",
        "Large bass with clear vocals and crisp hi-hats",
        (6, 4, 0, -1, 1, 2, 3),
        ("music", "bass"),
    ),
    SoundProfile(
        "edm",
        "EDM",
        "V-shaped electronic tuning with prominent sub, kick, and top end",
        (6, 4, -1, -2, 0, 3, 5),
        ("music", "electronic"),
    ),
    SoundProfile("pop", "Pop", "Tight, lively tuning with a subtle vocal lift", (3, 2, 0, 1, 2, 2.5, 3), ("music",)),
    SoundProfile(
        "jazz", "Jazz", "Natural warmth that preserves texture and ambience", (2, 1, 0.5, 1, 1, 1.5, 2), ("music",)
    ),
    SoundProfile(
        "classical",
        "Classical",
        "Neutral dynamics with added air and spatial definition",
        (0, 0, -0.5, 0, 1, 2, 3),
        ("music",),
    ),
    SoundProfile(
        "movie", "Cinema", "Low-end impact with dialogue presence and upper ambience", (5, 3, 0, 1, 3, 2, 3), ("media",)
    ),
    SoundProfile(
        "gaming",
        "Gaming / Footsteps",
        "Reduces masking bass and emphasizes the 2-4 kHz detail range",
        (0, -1, -2, 0, 4, 5, 2),
        ("gaming",),
    ),
    SoundProfile(
        "outdoor",
        "Outdoor",
        "Compensates for outdoor bass loss while retaining projection",
        (6, 4, 1, 0, 2, 3, 3),
        ("outdoor",),
    ),
    SoundProfile(
        "night",
        "Night / Apartment",
        "Reduces wall-transmitted sub-bass while preserving speech and detail",
        (-4.5, -3, -1, 1, 2, 1, 0),
        ("quiet",),
    ),
)

PROFILE_BY_KEY = {profile.key: profile for profile in PROFILES}


def get_profile(key: str) -> SoundProfile:
    try:
        return PROFILE_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"unknown sound profile {key!r}") from exc


def _interpolate(gains: tuple[float, ...], frequency: float) -> float:
    x = math.log2(frequency)
    points = [math.log2(value) for value in REFERENCE_FREQUENCIES]
    if x <= points[0]:
        return gains[0]
    if x >= points[-1]:
        return gains[-1]
    for index, (left, right) in enumerate(pairwise(points)):
        if left <= x <= right:
            ratio = (x - left) / (right - left)
            return gains[index] + ratio * (gains[index + 1] - gains[index])
    raise AssertionError("frequency interpolation interval not found")


def _model_frequencies(pid: str, count: int) -> list[float]:
    model = get_model(pid)
    features = set(model.get("features", []))
    if "EQ_BALANCE_SUPPORT" in features and "7_BANDS_EQ" not in features and "PROTOCOL_4" not in features:
        return [125.0, 1000.0, 8000.0]
    presets = presets_for_pid(pid)
    if presets and len(presets[0].get("params", [])) == count:
        return [float(param["frequency"]) for param in presets[0]["params"]]
    return list(REFERENCE_FREQUENCIES[:count])


def _quantize(value: float, step: float, low: float = -6.0, high: float = 6.0) -> float:
    return min(high, max(low, round(value / step) * step))


def resolve_profile(pid: str, profile_key: str) -> list[float]:
    """Map a seven-point tonal curve to a model's controls and legal steps."""
    profile = get_profile(profile_key)
    count = gain_count_for_pid(pid)
    if count == 0:
        raise ValueError(f"PID {pid} has no EQ controls declared by the APK")
    model = get_model(pid)
    normalized_pid = str(model.get("pid", "")).lower()
    features = set(model.get("features", []))
    values = [_interpolate(profile.gains, frequency) for frequency in _model_frequencies(pid, count)]

    integer_levels = "EQ_BALANCE_SUPPORT" in features or (
        "PRESET_EQ" in features and "7_BANDS_EQ" not in features and "PROTOCOL_4" not in features
    )
    if integer_levels:
        return [float(round(min(6, max(-6, value)))) for value in values]

    resolved = [_quantize(value, 0.5) for value in values]
    if normalized_pid == "20e3" or normalized_pid in GRIP_STYLE_P4_PIDS:
        first = values[0]
        resolved[0] = _quantize(first, 0.75, -9.0, 0.0) if first < 0 else _quantize(first, 0.5, 0.0, 6.0)
    return resolved


def profile_options() -> list[tuple[str, str]]:
    return [(profile.name, profile.key) for profile in PROFILES]


def sparkline(values: list[float]) -> str:
    # ASCII keeps curves readable in legacy Windows consoles and remote shells.
    blocks = ".:-=+*#@"
    return "".join(blocks[round((min(6.0, max(-6.0, value)) + 6.0) / 12.0 * (len(blocks) - 1))] for value in values)
