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

LAB_PROFILES = (
    SoundProfile(
        "lab-max-bass",
        "DANGER / Maximum Bass",
        "Extreme 125 Hz boost; bench testing only at very low playback volume",
        (24, 16, 4, -8, -12, -8, -2),
        ("danger", "bass", "lab"),
        True,
    ),
    SoundProfile(
        "lab-bass-cannon",
        "DANGER / Bass Cannon",
        "Maximum 250 Hz impact with aggressive low-frequency weight",
        (18, 24, 12, -4, -12, -8, 0),
        ("danger", "bass", "lab"),
        True,
    ),
    SoundProfile(
        "lab-kick-impact",
        "DANGER / Kick Impact",
        "Extreme kick and upper-bass emphasis with carved mids",
        (10, 24, 18, 0, -10, -6, 2),
        ("danger", "bass", "lab"),
        True,
    ),
    SoundProfile(
        "lab-deep-pressure",
        "DANGER / Deep Pressure",
        "Maximum lowest-band pressure with strongly reduced masking bands",
        (24, 12, 0, -10, -14, -8, -2),
        ("danger", "bass", "lab"),
        True,
    ),
    SoundProfile(
        "lab-extreme-v",
        "DANGER / Extreme V",
        "Maximum bass and air around a deeply recessed midrange",
        (24, 16, -12, -18, -12, 12, 24),
        ("danger", "v-shape", "lab"),
        True,
    ),
    SoundProfile(
        "lab-hyper-loudness",
        "DANGER / Hyper Loudness",
        "Very large low/high lift intended only for low-volume experiments",
        (18, 10, -8, -12, -6, 10, 18),
        ("danger", "loudness", "lab"),
        True,
    ),
    SoundProfile(
        "lab-air-24",
        "DANGER / Air +24",
        "Maximum 8 kHz shelf with progressively reduced low frequencies",
        (-12, -10, -8, 0, 8, 18, 24),
        ("danger", "treble", "lab"),
        True,
    ),
    SoundProfile(
        "lab-clarity-surgery",
        "DANGER / Clarity Surgery",
        "Severe low-mid cut and very strong presence/detail emphasis",
        (-10, -12, -16, -4, 12, 20, 16),
        ("danger", "clarity", "lab"),
        True,
    ),
    SoundProfile(
        "lab-vocal-megaphone",
        "DANGER / Vocal Megaphone",
        "Extreme 1-2 kHz vocal projection with bass suppression",
        (-18, -16, -12, 20, 24, 12, -8),
        ("danger", "voice", "lab"),
        True,
    ),
    SoundProfile(
        "lab-speech-extractor",
        "DANGER / Speech Extractor",
        "Maximum speech isolation curve for diagnostic listening",
        (-24, -18, -10, 18, 24, 16, -12),
        ("danger", "voice", "lab"),
        True,
    ),
    SoundProfile(
        "lab-mid-scoop",
        "DANGER / Mid Scoop",
        "Deep 500 Hz-2 kHz scoop with elevated frequency extremes",
        (12, 8, -18, -24, -18, 8, 12),
        ("danger", "scoop", "lab"),
        True,
    ),
    SoundProfile(
        "lab-mid-wall",
        "DANGER / Mid Wall",
        "Extreme 1-2 kHz emphasis for resonance and intelligibility tests",
        (-12, -8, 12, 24, 20, 4, -8),
        ("danger", "midrange", "lab"),
        True,
    ),
    SoundProfile(
        "lab-smile-24",
        "DANGER / Smile 24",
        "Maximum outer-band smile curve with a large center reduction",
        (24, 16, -8, -16, -8, 16, 24),
        ("danger", "v-shape", "lab"),
        True,
    ),
    SoundProfile(
        "lab-inverse-smile",
        "DANGER / Inverse Smile",
        "Maximum outer-band attenuation and elevated central bands",
        (-24, -16, 8, 16, 8, -16, -24),
        ("danger", "midrange", "lab"),
        True,
    ),
    SoundProfile(
        "lab-bass-delete",
        "LAB / Bass Delete",
        "Extreme low-frequency reduction for isolation and enclosure tests",
        (-24, -18, -12, -6, 0, 3, 6),
        ("lab", "cut", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-dark-24",
        "LAB / Dark 24",
        "Extreme upper-frequency reduction with a gently elevated low end",
        (6, 4, 2, 0, -8, -18, -24),
        ("lab", "dark", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-test-125",
        "DANGER / 125 Hz +24",
        "Single-band maximum boost for controlled bench diagnostics",
        (24, 0, 0, 0, 0, 0, 0),
        ("danger", "single-band", "lab"),
        True,
    ),
    SoundProfile(
        "lab-test-250",
        "DANGER / 250 Hz +24",
        "Single-band maximum boost for controlled bench diagnostics",
        (0, 24, 0, 0, 0, 0, 0),
        ("danger", "single-band", "lab"),
        True,
    ),
    SoundProfile(
        "lab-test-1k",
        "DANGER / 1 kHz +24",
        "Single-band maximum boost for controlled bench diagnostics",
        (0, 0, 0, 24, 0, 0, 0),
        ("danger", "single-band", "lab"),
        True,
    ),
    SoundProfile(
        "lab-test-8k",
        "DANGER / 8 kHz +24",
        "Single-band maximum boost for controlled bench diagnostics",
        (0, 0, 0, 0, 0, 0, 24),
        ("danger", "single-band", "lab"),
        True,
    ),
    # Everything above spends the extended range on boost, which is the one thing
    # it is bad at: a large boost overruns the DSP and the speaker's limiter, so
    # it distorts and then gets quieter. The profiles below spend it on cuts
    # instead, which is what the range is actually good for -- a cut cannot clip,
    # and the standard +/-6 dB simply cannot reach far enough to fix a real room
    # or a real resonance. Raise the volume knob to make up the level.
    SoundProfile(
        "lab-tilt-bass",
        "LAB / Subtractive Bass",
        "Bass-forward by cutting everything above it, then turning the volume up",
        (0, -3, -7, -10, -12, -12, -10),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-tilt-dark",
        "LAB / Subtractive Dark",
        "Warm and relaxed by lowering the top end rather than lifting the bass",
        (0, 0, -2, -5, -9, -14, -18),
        ("lab", "dark", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-corner-fix",
        "LAB / Corner Placement Fix",
        "Removes the low-end lift a corner or nearby wall adds to the speaker",
        (-12, -7, -2, 0, 0, 0, 0),
        ("lab", "placement", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-boom-notch",
        "LAB / Room Boom Notch",
        "Deep 250 Hz notch for a one-note room resonance; sweep 125/250 to taste",
        (-6, -16, -5, 0, 0, 0, 0),
        ("lab", "placement", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-mud-cut",
        "LAB / Mud Cut",
        "Clears 500 Hz congestion so voices and guitars stop sounding boxy",
        (0, -5, -14, -5, 0, 0, 0),
        ("lab", "clarity", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-harsh-cut",
        "LAB / Harshness Cut",
        "Tames the 2-4 kHz shout that makes small speakers tiring to listen to",
        (0, 0, 0, -2, -13, -7, 0),
        ("lab", "clarity", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-de-ess",
        "LAB / De-Ess",
        "Deep 4-8 kHz cut for recordings with harsh, spitty sibilance",
        (0, 0, 0, 0, -2, -9, -14),
        ("lab", "clarity", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-night",
        "LAB / Night Mode",
        "Drops the low end that carries through walls; keeps the rest intact",
        (-22, -12, -3, 0, 0, -2, -5),
        ("lab", "quiet", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-speech-clear",
        "LAB / Speech Clarity",
        "Podcasts and audiobooks: removes rumble and hiss around the voice",
        (-16, -9, -2, 1, 0, -4, -11),
        ("lab", "voice", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-vocal-forward",
        "LAB / Vocal Forward",
        "Brings vocals forward by lowering what surrounds them, not by boosting",
        (-12, -8, -3, 0, 0, -4, -9),
        ("lab", "voice", "subtractive"),
        True,
    ),
    # The bass family. Every one of these gets its weight by lowering the bands
    # above 125 Hz and leaving 125 Hz alone -- the tilt is what the ear hears as
    # "bass", and a tilt built from cuts costs level instead of headroom. Turn
    # the volume up afterwards; the speaker has the level to give, it does not
    # have the headroom to fake a +24 dB lift.
    SoundProfile(
        "lab-tilt-bass-deep",
        "LAB / Subtractive Bass Deep",
        "A heavier tilt than Subtractive Bass; expect to add roughly 15 dB of volume",
        (0, -2, -9, -15, -18, -18, -16),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-tilt-bass-extreme",
        "LAB / Subtractive Bass Extreme",
        "The deepest clean tilt available; everything but the low end is far down",
        (0, -4, -13, -19, -23, -24, -22),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-basshead",
        "LAB / Basshead",
        "Massive low-end character with the harsh upper mids pulled furthest down",
        (0, -5, -14, -20, -24, -22, -18),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-sub-focus",
        "LAB / Sub Focus",
        "Low band only; acts like a lowpass for feeling bass rather than hearing music",
        (0, -9, -18, -23, -24, -24, -24),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-punch-sub",
        "LAB / Subtractive Punch",
        "Keeps 125 and 250 Hz together for kick weight rather than pure depth",
        (0, 0, -9, -14, -16, -15, -13),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-warm-sub",
        "LAB / Subtractive Warm",
        "Bass and low mids intact with a long roll-off; smooth and non-fatiguing",
        (0, -1, -5, -11, -16, -20, -22),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-808-sub",
        "LAB / Subtractive 808",
        "Deep low end with the low mids scooped so 808s stay clean and separate",
        (0, -7, -15, -17, -15, -13, -11),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-dub-sub",
        "LAB / Subtractive Dub",
        "Big bass under a steadily darkening top end; reggae and dub character",
        (0, -2, -9, -14, -18, -22, -24),
        ("lab", "bass", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-club-sub",
        "LAB / Subtractive Club",
        "Bass and air around scooped mids; the classic club curve without clipping",
        (0, -6, -15, -19, -15, -9, -5),
        ("lab", "bass", "subtractive"),
        True,
    ),
    # Genre curves. These are taste, not measurement -- they shape tone the way
    # the style is usually mixed, and nothing more is claimed for them.
    SoundProfile(
        "lab-hiphop-sub",
        "LAB / Hip-Hop",
        "Low-end weight with the mids held back so vocals sit on top of the beat",
        (0, -2, -10, -14, -14, -12, -9),
        ("lab", "genre", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-edm-sub",
        "LAB / EDM",
        "Bass and top-end sparkle with a deep midrange scoop between them",
        (0, -6, -14, -17, -13, -8, -4),
        ("lab", "genre", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-metal-sub",
        "LAB / Metal",
        "Tight low end, scooped low mids, and guitars left with their bite",
        (0, -3, -12, -14, -8, -6, -8),
        ("lab", "genre", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-acoustic-sub",
        "LAB / Acoustic",
        "Rumble and harshness removed so guitars and voices stay natural",
        (-10, -4, 0, 0, -4, -8, -6),
        ("lab", "genre", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-classical-sub",
        "LAB / Classical",
        "Gentle, mostly untouched mids with rumble and top-end edge removed",
        (-8, -3, 0, 0, 0, -3, -8),
        ("lab", "genre", "subtractive"),
        True,
    ),
    # Situation curves: the room and the placement, not the music.
    SoundProfile(
        "lab-outdoor",
        "LAB / Outdoors",
        "No walls to reinforce the bass, so the rest comes down to rebalance it",
        (0, -2, -8, -12, -14, -14, -12),
        ("lab", "placement", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-tiled-room",
        "LAB / Tiled Room",
        "Bathrooms and kitchens: tames boom and the glare hard surfaces add",
        (-8, -10, -4, 0, -6, -12, -16),
        ("lab", "placement", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-shelf-fix",
        "LAB / Shelf / Against Wall",
        "Milder than the corner fix; for one nearby boundary instead of two",
        (-9, -5, -1, 0, 0, 0, 0),
        ("lab", "placement", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-desk-fix",
        "LAB / Desk Bounce",
        "Cuts the 250 Hz thickening a desk or table reflects back at you",
        (-4, -10, -4, 0, 0, 0, 0),
        ("lab", "placement", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-gaming-steps",
        "LAB / Game Footsteps",
        "Drops explosions and hiss so footsteps and cues sit in front",
        (-16, -12, -4, 0, 0, -2, -10),
        ("lab", "use-case", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-movie-dialogue",
        "LAB / Movie Dialogue",
        "Rumble and effects pulled back so speech stays intelligible at low volume",
        (-10, -6, 0, 1, 0, -4, -10),
        ("lab", "use-case", "subtractive"),
        True,
    ),
    # Single-problem repairs. Sweep the neighbouring band if the fix lands slightly off.
    SoundProfile(
        "lab-rumble-cut",
        "LAB / Rumble Cut",
        "Removes handling, wind, and traffic rumble under the music",
        (-18, -6, 0, 0, 0, 0, 0),
        ("lab", "repair", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-driver-protect",
        "LAB / Driver Protection",
        "Deep low cut so a small driver stops bottoming out at high volume",
        (-20, -10, -3, 0, 0, 0, 0),
        ("lab", "repair", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-honk-cut",
        "LAB / Honk Cut",
        "Removes the 1 kHz cupped-hands honk small enclosures add",
        (0, 0, -6, -13, -4, 0, 0),
        ("lab", "repair", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-hiss-cut",
        "LAB / Hiss Cut",
        "Drops 8 kHz tape hiss and codec noise without dulling the whole top",
        (0, 0, 0, 0, 0, -6, -16),
        ("lab", "repair", "subtractive"),
        True,
    ),
    # The "expensive speaker" family.
    #
    # EQ cannot buy a better driver, a stiffer cabinet or more resolution. What
    # an expensive speaker mostly has is an ABSENCE: no port boom, no boxy
    # colouration, no upper-mid shout, no fake sizzle. A portable speaker is
    # deliberately tuned the opposite way -- a smiley curve that stands out on a
    # shop shelf. Taking that tuning back off is the one thing EQ genuinely does
    # well, and it is all cuts, so it costs nothing in headroom.
    #
    # The room curves below are not invented: Harman's own listener panels (JBL
    # is Harman) found people prefer an in-room response with a low shelf and a
    # gentle downward tilt rather than a literally flat one. They are expressed
    # subtractively here, which is also how a mastering room gets there.
    SoundProfile(
        "lab-harman-room",
        "LAB / Harman Room Curve",
        "Harman's own preference target: low shelf under a gentle downward tilt",
        (0, -2, -5, -6, -7, -8, -10),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-reference-tilt",
        "LAB / Reference Tilt",
        "The steeper studio room slope; drier and more neutral than the Harman curve",
        (0, -2, -4, -6, -8, -10, -12),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-neutral-fix",
        "LAB / Neutral Correction",
        "Takes the shop-shelf smiley back off: no boom, no sizzle, mids left alone",
        (-8, -11, -2, 0, -3, -8, -10),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-studio-dry",
        "LAB / Studio Reference",
        "Monitor-like and unflattering; shows what a recording actually contains",
        (-5, -9, -3, 0, -1, -4, -7),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-tight-bass",
        "LAB / Tight Bass",
        "Kills the port boom so bass lines are articulate instead of one note",
        (-4, -14, -5, 0, 0, 0, 0),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-detail-no-glare",
        "LAB / Detail Without Glare",
        "Removes the 2 kHz shout that reads as detail but is really fatigue",
        (0, -3, -4, -3, -12, -7, -2),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-silk-treble",
        "LAB / Silk Treble",
        "Takes out the 4 kHz sizzle that fakes air; the real top end stays",
        (0, 0, -2, -3, -5, -13, -8),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-vocal-purity",
        "LAB / Vocal Purity",
        "Clears the boom and boxiness around a voice and leaves the voice untouched",
        (-7, -11, -8, 0, -2, -7, -10),
        ("lab", "reference", "subtractive"),
        True,
    ),
    SoundProfile(
        "lab-night-hifi",
        "LAB / Late Night Hi-Fi",
        "Quiet listening that stays clean rather than lifting the extremes to fake it",
        (-15, -9, -3, 0, -1, -5, -9),
        ("lab", "reference", "subtractive"),
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
