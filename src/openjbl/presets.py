"""Curated tonal profiles resolved safely against each model's EQ controls."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from .models import GRIP_STYLE_P4_PIDS, gain_count_for_pid, get_model, presets_for_pid

REFERENCE_FREQUENCIES = (125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0)
# The largest boost any model's own UI offers. Past this a lift has to come out
# of the DSP's headroom and the speaker's limiter, so it can clip.
STANDARD_MAX_BOOST_DB = 6.0


@dataclass(frozen=True)
class SoundProfile:
    key: str
    name: str
    description: str
    gains: tuple[float, float, float, float, float, float, float]
    tags: tuple[str, ...] = ()
    # LAB tier: needs the float-parametric encoder because it leaves the model's
    # own step/range grid. NOT the same question as whether it can damage
    # anything -- see boosts_past_standard.
    dangerous: bool = False

    @property
    def boosts_past_standard(self) -> bool:
        """Whether this curve lifts a band beyond what the model's UI allows.

        This is what earns the confirmation step, not LAB membership. A boost is
        paid for out of headroom and can clip; a cut of any depth cannot -- it
        only costs level, which the volume knob gives back.
        """
        return any(gain > STANDARD_MAX_BOOST_DB for gain in self.gains)


# The catalog is curated: one curve per job, and a job that two curves could do
# is done by the better one. The standard tier is the everyday set every EQ model
# can play inside its own app's range, and is the one to reach for at full
# volume -- it does not trade loudness for tone. The LAB tier is the precise set.
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
        "vocal",
        "Vocal Focus",
        "Brings vocals and dialogue forward while reducing masking bass",
        (-0.75, -1, -1, 3, 4, 2, 0),
        ("voice",),
    ),
    SoundProfile(
        "outdoor",
        "Outdoor",
        "Compensates for outdoor bass loss while retaining projection",
        (6, 4, 1, 0, 2, 3, 3),
        ("outdoor",),
    ),
)

# The LAB tier: cuts only, every one of them.
#
# EQ cannot buy a better driver, a stiffer cabinet or more resolution. What an
# expensive speaker mostly has is an ABSENCE: no port boom, no boxy colouration,
# no upper-mid shout, no fake sizzle. A portable speaker is deliberately tuned
# the opposite way -- a smiley curve that stands out on a shop shelf. Taking that
# tuning back off is the one thing EQ genuinely does well, and a cut costs level,
# which the volume knob gives back, rather than headroom, which it cannot. A
# boost past the standard range overruns the DSP and the limiter, so it distorts
# and then gets quieter; none is offered here. Typing one into the gain field
# still works, behind the DANGER confirmation.
#
# The fitted curves below were not picked band by band. Each started as a
# continuous target response, and its gains were solved for against the Charge 6
# filter chain the speaker actually runs (custom_c2_eq.json: a 125 Hz low shelf,
# Q2 peaks at 250 Hz-4 kHz and an 8 kHz high shelf, at 48 kHz), then rounded to
# 0.5 dB. That matters because Q2 peaks an octave apart do not join up: a broad
# cut built from several of them ripples by 2-3 dB between the centres, so a
# hand-picked curve is not the response that ships. The curves that lean on the
# shelves land within about 1 dB of their target; the broad tilts cannot do
# better than the ripple. Other float-parametric models get the same seven-point
# curve interpolated onto their own bands.
LAB_PROFILES = (
    # The reference pair: the speaker's own colouration taken back off.
    #
    # Harman's listener panels (JBL is Harman) found people prefer an in-room
    # response with a low shelf under a gentle downward tilt rather than a
    # literally flat one. It is expressed subtractively here, which is also how a
    # mastering room gets there.
    SoundProfile(
        "lab-harman-room",
        "LAB / Harman Room Curve",
        "Harman's own preference target: low shelf under a gentle downward tilt",
        (0, -2, -5, -6, -7, -8, -10),
        ("lab", "reference", "subtractive"),
        True,
    ),
    # The room family: other published in-room targets, each the sound of a
    # particular kind of room, fitted the same way as the curves further down.
    # They are the target's shape laid over the speaker, not a measured room
    # correction -- there is no microphone in the loop.
    #
    # Fitted to Olive, Welti & McMullin (AES 2013), the listening test behind
    # the Harman curve: the average preferred in-room response, +6.6 dB below
    # 105 Hz and -2.4 dB above 2.5 kHz, flat between. Against the gradual tilt
    # above it, the mids stay level, so the low end reads as a solid shelf of
    # punch and the 1-2 kHz range sits further forward. Fit: 1.4 dB rms, the Q2
    # ripple across the broad mid cut.
    SoundProfile(
        "lab-harman-2013",
        "LAB / Harman Listener Target",
        "Harman's 2013 listening-test result: solid bass shelf, level mids, treble step",
        (0, -5.5, -4.5, -4.5, -4, -8, -9),
        ("lab", "reference", "room", "subtractive"),
        True,
    ),
    # Fitted to Bruel & Kjaer's 1974 "optimum curve for hi-fi in the listening
    # room": flat to 160 Hz, then a straight slope to -6 dB at 20 kHz. Toole's
    # estimate for a reflective domestic room lands within a dB of it. Lighter
    # than Harman everywhere above 500 Hz: more open, less bass-forward.
    # Fit: 0.6 dB rms.
    SoundProfile(
        "lab-bk-house",
        "LAB / B&K House Curve",
        "The classic 1974 hi-fi room: flat to 160 Hz, then a straight gentle slope",
        (0, 0, -1, -2, -2.5, -4, -6.5),
        ("lab", "reference", "room", "subtractive"),
        True,
    ),
    # Fitted to the Dolby Atmos Music target for small mixing rooms: +1 dB below
    # 160 Hz, flat to 1.6 kHz, -1.5 dB/octave to 10 kHz, -3 dB/octave above.
    # The nearest thing to what the mix engineer heard; the most neutral of the
    # family. Fit: 0.4 dB rms.
    SoundProfile(
        "lab-music-studio",
        "LAB / Music Studio Room",
        "Dolby's music mixing-room curve: flat through the mids, gentle top roll-off",
        (0, -0.5, -0.5, -0.5, -1, -3, -6.5),
        ("lab", "reference", "room", "subtractive"),
        True,
    ),
    # Fitted to the SMPTE ST 202 X-curve for large cinemas: flat to 2 kHz, then
    # -3 dB/octave to 10 kHz and -6 dB/octave above. The mids keep their full
    # weight while the top softens the way a big auditorium's does.
    # Fit: 0.5 dB rms.
    SoundProfile(
        "lab-cinema-x",
        "LAB / Cinema X-Curve",
        "The movie-theatre room: full mids, highs rolling off above 2 kHz like a big hall",
        (0, 0, 0, 0, 0, -3.5, -10.5),
        ("lab", "reference", "room", "subtractive"),
        True,
    ),
    # Fitted to Archimago's "Vocal Bloom" target (2026): bass shelf kept, a
    # +2 dB bloom at 700 Hz-1 kHz where voices carry their body, and a taper
    # from 3 kHz that softens presence and treble. An intimate, small-club room.
    # Fit: 0.6 dB rms.
    SoundProfile(
        "lab-vocal-bloom",
        "LAB / Vocal Bloom Room",
        "A warm, intimate room: bass kept, voices bloom at 1 kHz, soft presence and top",
        (0, -2, -1.5, 0, -0.5, -3.5, -7),
        ("lab", "reference", "room", "subtractive"),
        True,
    ),
    # The Harman curve's top end is what keeps it from sounding clear: past 2 kHz
    # it keeps falling. This one spends its depth on the 250-500 Hz mud and box
    # instead, leaves 1 kHz standing above its neighbours so voices come forward,
    # trims the 4 kHz sizzle, and lets 8 kHz air back up past the mids.
    SoundProfile(
        "lab-hifi-clarity",
        "LAB / Hi-Fi Clarity",
        "Clears the mud and box, keeps the bass, opens the air: clean and transparent",
        (0, -6, -7, -4, -5, -5, -3),
        ("lab", "reference", "subtractive"),
        True,
    ),
    # Fitted to: 50-100 Hz 0, 200 Hz -5, 300 Hz -9, 500 Hz -11, then -10 to
    # -9 through 4.5 kHz, rising to -7 above 12 kHz. A 10 dB bass-to-mids tilt
    # is the weight; the 500 Hz trough is what keeps it from going one-note, and
    # the top sitting slightly above the mids keeps the kick's click audible.
    # Expect to add about 10 dB of volume. Fit: 1.5 dB rms, the Q2 ripple.
    SoundProfile(
        "lab-bass",
        "LAB / Deep Clean Bass",
        "A 10 dB bass tilt built from cuts, with the 500 Hz mud scooped so it stays tight",
        (0, -6, -10.5, -8.5, -8.5, -9, -8),
        ("lab", "bass", "subtractive"),
        True,
    ),
    # Fitted to: 50 Hz -7, 140 Hz -3, 200-300 Hz -1.5, 500 Hz -3, 1 kHz -1,
    # 1.5-3 kHz 0, 6.5 kHz -2, 14 kHz 0. Bass instruments are what mask a voice,
    # so they come down; the 200-300 Hz warmth of the voice itself does not.
    # The 500 Hz box goes, 1.5-3 kHz presence and the breath above 10 kHz stay.
    # For music with singers. Fit: 0.5 dB rms.
    SoundProfile(
        "lab-vocal",
        "LAB / Vocal Presence",
        "Singers up front: bass and box pulled back, voice warmth and air untouched",
        (-7, -0.5, -3, -0.5, 0, -0.5, -0.5),
        ("lab", "voice", "subtractive"),
        True,
    ),
    # Fitted to: below 100 Hz -2, 250 Hz -7, 400 Hz -4, 1-3 kHz 0, 9 kHz -4.
    # The opposite trade to Vocal Presence: explosions keep their weight, and
    # the 250 Hz boom -- where chesty dialogue and this speaker's bloom pile up
    # -- is what gets cut. The top comes down for hiss and harsh effects.
    # Fit: 0.6 dB rms.
    SoundProfile(
        "lab-movie",
        "LAB / Cinema Dialogue",
        "Clear dialogue that keeps explosion weight: the boomy 250 Hz region removed",
        (-2, -7.5, -2, 0, 0, -0.5, -4.5),
        ("lab", "media", "subtractive"),
        True,
    ),
    # Fitted to: 50 Hz -16, 150 Hz -10, 250 Hz -6, 0.7-3 kHz 0, 4.5 kHz -2,
    # 7 kHz -7, -10 above 10 kHz. Close-mic voices carry proximity boom and
    # nothing useful below 150 Hz; above 6 kHz is sibilance, mouth noise and
    # hiss. Talk only -- it will gut music. Fit: 1.0 dB rms.
    SoundProfile(
        "lab-speech",
        "LAB / Podcast & Speech",
        "Talk only: rumble and hiss removed, the 500 Hz-3 kHz voice band untouched",
        (-19, -5, 0, 0, 0, -0.5, -12.5),
        ("lab", "voice", "subtractive"),
        True,
    ),
    # Fitted to: 50-100 Hz -14, 250 Hz -7, 0.4-1 kHz -3 to -4, 2-4.5 kHz 0,
    # 8 kHz -4, -6 above 12 kHz. Footsteps, reloads and positional cues live in
    # the 2-4 kHz clicks; explosions and engine rumble mask them. Unlike Podcast
    # & Speech it lowers 500 Hz-1 kHz too, so the cue band stands above the
    # voice band rather than level with it. Fit: 1.0 dB rms.
    SoundProfile(
        "lab-gaming",
        "LAB / Gaming Footsteps",
        "Explosions and rumble pulled down so 2-4 kHz footsteps and cues stand out",
        (-17.5, -6.5, -3, -2.5, 0, 0, -6.5),
        ("lab", "gaming", "subtractive"),
        True,
    ),
    # Fitted to: 50 Hz -18, 125 Hz -10, 180 Hz -5, 250 Hz -2.5, flat from
    # 700 Hz up, -1 above 10 kHz. Walls stop the treble and pass the bass, so
    # the bass is the part a neighbour hears; what a listener in the room needs
    # -- voices, instruments, detail -- sits above 250 Hz and is left alone.
    # Fit: 0.2 dB rms.
    SoundProfile(
        "lab-night",
        "LAB / Late Night",
        "Removes the bass that travels through walls; everything above 250 Hz intact",
        (-19, -1, -0.5, 0, 0, 0, -1),
        ("lab", "quiet", "subtractive"),
        True,
    ),
)

ALL_PROFILES = PROFILES + LAB_PROFILES
PROFILE_BY_KEY = {profile.key: profile for profile in ALL_PROFILES}


def get_profile(key: str) -> SoundProfile:
    try:
        return PROFILE_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"unknown sound profile {key!r}") from exc


def _interpolate_at(frequencies: Sequence[float], gains: Sequence[float], frequency: float) -> float:
    """Read `gains` (sampled at `frequencies`) at an arbitrary frequency.

    Interpolation is done in log-frequency because that is how octaves -- and
    hearing -- are spaced.
    """
    x = math.log2(frequency)
    points = [math.log2(value) for value in frequencies]
    if x <= points[0]:
        return float(gains[0])
    if x >= points[-1]:
        return float(gains[-1])
    for index, (left, right) in enumerate(pairwise(points)):
        if left <= x <= right:
            ratio = (x - left) / (right - left)
            return float(gains[index] + ratio * (gains[index + 1] - gains[index]))
    raise AssertionError("frequency interpolation interval not found")


def _interpolate(gains: tuple[float, ...], frequency: float) -> float:
    return _interpolate_at(REFERENCE_FREQUENCIES, gains, frequency)


def curve_from_model_gains(pid: str, gains: Sequence[float]) -> tuple[float, ...]:
    """Resample a model's own gain list back onto the reference seven-point grid.

    A saved profile has to outlive the speaker it was made on, so it is stored as
    a tonal curve rather than as one model's band values. For a model whose bands
    already sit on the reference grid this is the identity.
    """
    if not gains:
        raise ValueError("cannot build a profile from an empty gain list")
    # Against the model's declared band count, not against len(gains). Asking
    # _model_frequencies for len(gains) frequencies and then checking it returned
    # len(gains) of them is a tautology: it made a three-value list on a
    # seven-band speaker pass, and four bands the user never typed got invented
    # by the interpolator and later written to hardware.
    count = gain_count_for_pid(pid)
    if count == 0:
        raise ValueError(f"PID {pid} has no EQ controls declared by the APK")
    if len(gains) != count:
        raise ValueError(f"PID {pid} has {count} bands; received {len(gains)} gains")
    frequencies = _model_frequencies(pid, count)
    if len(gains) == 1:
        return tuple(float(gains[0]) for _ in REFERENCE_FREQUENCIES)
    return tuple(round(_interpolate_at(frequencies, gains, value), 3) for value in REFERENCE_FREQUENCIES)


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
    """Map a built-in profile's curve to a model's controls and legal steps."""
    return resolve_curve(pid, get_profile(profile_key))


def resolve_curve(pid: str, profile: SoundProfile) -> list[float]:
    """Map any profile's curve to a model's controls and legal steps.

    Takes the profile rather than its key so a user-created one -- which cannot
    live in the built-in registry -- resolves through exactly the same path, and
    therefore gets the same range and step checks.
    """
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
    if profile.dangerous:
        if integer_levels or normalized_pid in GRIP_STYLE_P4_PIDS:
            raise ValueError("extended-range profiles require a float-parametric EQ protocol")
        if any(not -24.0 <= value <= 24.0 for value in values):
            raise ValueError("profile exceeds the protocol's conservative +/-24 dB bound")
        return [round(value, 3) for value in values]
    if integer_levels:
        return [float(round(min(6, max(-6, value)))) for value in values]

    resolved = [_quantize(value, 0.5) for value in values]
    if normalized_pid == "20e3" or normalized_pid in GRIP_STYLE_P4_PIDS:
        first = values[0]
        resolved[0] = _quantize(first, 0.75, -9.0, 0.0) if first < 0 else _quantize(first, 0.5, 0.0, 6.0)
    return resolved


def profile_options(*, dangerous: bool = False) -> list[tuple[str, str]]:
    profiles = LAB_PROFILES if dangerous else PROFILES
    return [(profile.name, profile.key) for profile in profiles]


def curve_summary(gains: Sequence[float]) -> str:
    """One line describing what a curve does, for a profile the user just made."""
    # Both ends are described relative to the mids, because that is what the ear
    # judges tone against -- not against zero.
    bass = sum(gains[:2]) / 2 - sum(gains[2:5]) / 3
    treble = sum(gains[-2:]) / 2 - sum(gains[2:5]) / 3
    if bass >= 3 and treble >= 3:
        shape = "V-shaped"
    elif bass <= -3 and treble <= -3:
        shape = "mid-forward"
    elif bass >= 3 and treble <= -3:
        # Both ends move the same way across the spectrum: a slope, not a bass lift.
        shape = "dark tilt"
    elif bass <= -3 and treble >= 3:
        shape = "bright tilt"
    elif bass >= 3:
        shape = "bass-forward"
    elif bass <= -3:
        shape = "bass-light"
    elif treble >= 3:
        shape = "bright"
    elif treble <= -3:
        shape = "dark"
    else:
        shape = "flat"
    span = max(gains) - min(gains)
    return f"{shape}, {span:.0f} dB span, {min(gains):+g} .. {max(gains):+g} dB"


def sparkline(values: list[float]) -> str:
    # ASCII keeps curves readable in legacy Windows consoles and remote shells.
    blocks = ".:-=+*#@"
    limit = max(6.0, *(abs(value) for value in values))
    return "".join(
        blocks[round((min(limit, max(-limit, value)) + limit) / (2 * limit) * (len(blocks) - 1))] for value in values
    )
