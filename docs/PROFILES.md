# Sound profiles

A profile is a seven-point tonal curve sampled at 125, 250, 500, 1k, 2k, 4k and
8 kHz. The resolver interpolates it in log-frequency space, then quantizes the
result to whatever the selected model can actually express:

- **Charge 6 and Grip-style**: band 1 takes +0.5 / -0.75 dB steps; other bands 0.5 dB.
- **Protocol 4 and legacy parametric**: 0.5 dB within -6..+6 dB.
- **Simple 3-band and advanced-level**: integer levels within -6..+6.
- **Five-band models**: their own preset frequencies, not a truncated seven-band curve.

Run `openjbl profiles --pid YOUR_PID` to see what a profile resolves to on your
speaker. This file is generated from the code, so the curves below are the ones
that ship.

These are tonal starting points. Nothing here overclocks an amplifier or bypasses
a limiter.

## Standard (24)

Inside every model's own UI range, so they apply with a single click.

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `flat` | Flat / Reference | 0, 0, 0, 0, 0, 0, 0 | No tonal shaping; use this as a level-checking baseline |
| `balanced` | Balanced | 1, 0.5, 0, 0, 0, 0.5, 1 | Even, fatigue-free tuning with no strongly emphasized range |
| `bass` | Bass Heavy | 6, 4, 1, -1, -1, 0, 1 | Strong 125-250 Hz weight with restrained mids to limit muddiness |
| `deep-bass` | Deep Bass | 6, 3, 0, -2, -1, 0, 0.5 | Deeper low-end weight with reduced low-mids for additional space |
| `punch` | Punch Bass | 4, 5, 2, -1, -1, 0.5, 1 | Tight impact focused on kick and rhythm rather than bloom |
| `warm` | Warm | 3, 2, 1, 0.5, 0, -0.5, -1 | Smooth and relaxed with reduced upper-range bite |
| `loudness` | Low-volume Loudness | 4, 2, 0, -1, 0, 1.5, 3 | Lifts both extremes to compensate at low playback levels |
| `clear` | Crystal Clear | 0, -1, -2, 0, 2, 3, 4 | Reduces low-mid congestion and adds presence and air |
| `bright` | Bright | -0.75, -0.5, -1, 0, 2, 4, 5 | Open and prominent top end for dark-sounding sources |
| `detail` | Detail Monitor | -1.5, -1, -1, 1, 2, 2.5, 2 | Analytical tuning with reduced excess bass and moderate upper-mid lift |
| `vocal` | Vocal Focus | -0.75, -1, -1, 3, 4, 2, 0 | Brings vocals and dialogue forward while reducing masking bass |
| `podcast` | Podcast / Speech | -3, -2, -1, 3, 4, 2, -1 | Prioritizes speech intelligibility and reduces rumble |
| `acoustic` | Acoustic | 1, 1, 0.5, 1, 1.5, 2, 2 | Preserves instrument body while adding upper detail |
| `rock` | Rock | 4, 3, -1, 1, 3, 3, 2 | Clear kick and guitars with impact and an open top end |
| `metal` | Metal | 3, 1, -2, 0, 3, 4, 2 | Controls low-mid guitar overlap and emphasizes attack |
| `hip-hop` | Hip-Hop | 6, 4, 0, -1, 1, 2, 3 | Large bass with clear vocals and crisp hi-hats |
| `edm` | EDM | 6, 4, -1, -2, 0, 3, 5 | V-shaped electronic tuning with prominent sub, kick, and top end |
| `pop` | Pop | 3, 2, 0, 1, 2, 2.5, 3 | Tight, lively tuning with a subtle vocal lift |
| `jazz` | Jazz | 2, 1, 0.5, 1, 1, 1.5, 2 | Natural warmth that preserves texture and ambience |
| `classical` | Classical | 0, 0, -0.5, 0, 1, 2, 3 | Neutral dynamics with added air and spatial definition |
| `movie` | Cinema | 5, 3, 0, 1, 3, 2, 3 | Low-end impact with dialogue presence and upper ambience |
| `gaming` | Gaming / Footsteps | 0, -1, -2, 0, 4, 5, 2 | Reduces masking bass and emphasizes the 2-4 kHz detail range |
| `outdoor` | Outdoor | 6, 4, 1, 0, 2, 3, 3 | Compensates for outdoor bass loss while retaining projection |
| `night` | Night / Apartment | -4.5, -3, -1, 1, 2, 1, 0 | Reduces wall-transmitted sub-bass while preserving speech and detail |

## LAB (63)

Beyond the model's UI range, out to +/-24 dB. These need `--allow-extended` on the
CLI, and only work on float-parametric models -- a level-index encoder has no way
to express them.

### Why most of these only cut

A large boost has to come from somewhere. It eats the DSP's headroom and runs into
the speaker's limiter, so +24 dB at 125 Hz does not give you more bass: it gives
you distortion, and then less level than you started with.

A cut cannot clip. It costs level, and the volume knob gives that back. So what a
+/-24 dB range is really good for is the reach it gives you *downward* -- far
enough to pull out a room resonance or a port boom that +/-6 dB cannot touch.

The bass family leaves 125 Hz at 0 dB and lowers everything above it. The tilt is
what the ear hears as bass, and a tilt built from cuts is the same tilt without
the distortion. Turn the volume up afterwards.

### Cut-based (45)

Single click; a cut cannot clip.

#### Bass

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-tilt-bass` | LAB / Subtractive Bass | 0, -3, -7, -10, -12, -12, -10 | Bass-forward by cutting everything above it, then turning the volume up |
| `lab-tilt-bass-deep` | LAB / Subtractive Bass Deep | 0, -2, -9, -15, -18, -18, -16 | A heavier tilt than Subtractive Bass; expect to add roughly 15 dB of volume |
| `lab-tilt-bass-extreme` | LAB / Subtractive Bass Extreme | 0, -4, -13, -19, -23, -24, -22 | The deepest clean tilt available; everything but the low end is far down |
| `lab-basshead` | LAB / Basshead | 0, -5, -14, -20, -24, -22, -18 | Massive low-end character with the harsh upper mids pulled furthest down |
| `lab-sub-focus` | LAB / Sub Focus | 0, -9, -18, -23, -24, -24, -24 | Low band only; acts like a lowpass for feeling bass rather than hearing music |
| `lab-punch-sub` | LAB / Subtractive Punch | 0, 0, -9, -14, -16, -15, -13 | Keeps 125 and 250 Hz together for kick weight rather than pure depth |
| `lab-warm-sub` | LAB / Subtractive Warm | 0, -1, -5, -11, -16, -20, -22 | Bass and low mids intact with a long roll-off; smooth and non-fatiguing |
| `lab-808-sub` | LAB / Subtractive 808 | 0, -7, -15, -17, -15, -13, -11 | Deep low end with the low mids scooped so 808s stay clean and separate |
| `lab-dub-sub` | LAB / Subtractive Dub | 0, -2, -9, -14, -18, -22, -24 | Big bass under a steadily darkening top end; reggae and dub character |
| `lab-club-sub` | LAB / Subtractive Club | 0, -6, -15, -19, -15, -9, -5 | Bass and air around scooped mids; the classic club curve without clipping |

#### Clean and uncoloured

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-harman-room` | LAB / Harman Room Curve | 0, -2, -5, -6, -7, -8, -10 | Harman's own preference target: low shelf under a gentle downward tilt |
| `lab-reference-tilt` | LAB / Reference Tilt | 0, -2, -4, -6, -8, -10, -12 | The steeper studio room slope; drier and more neutral than the Harman curve |
| `lab-neutral-fix` | LAB / Neutral Correction | -8, -11, -2, 0, -3, -8, -10 | Takes the shop-shelf smiley back off: no boom, no sizzle, mids left alone |
| `lab-studio-dry` | LAB / Studio Reference | -5, -9, -3, 0, -1, -4, -7 | Monitor-like and unflattering; shows what a recording actually contains |
| `lab-tight-bass` | LAB / Tight Bass | -4, -14, -5, 0, 0, 0, 0 | Kills the port boom so bass lines are articulate instead of one note |
| `lab-detail-no-glare` | LAB / Detail Without Glare | 0, -3, -4, -3, -12, -7, -2 | Removes the 2 kHz shout that reads as detail but is really fatigue |
| `lab-silk-treble` | LAB / Silk Treble | 0, 0, -2, -3, -5, -13, -8 | Takes out the 4 kHz sizzle that fakes air; the real top end stays |
| `lab-vocal-purity` | LAB / Vocal Purity | -7, -11, -8, 0, -2, -7, -10 | Clears the boom and boxiness around a voice and leaves the voice untouched |
| `lab-night-hifi` | LAB / Late Night Hi-Fi | -15, -9, -3, 0, -1, -5, -9 | Quiet listening that stays clean rather than lifting the extremes to fake it |

#### Room and placement

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-corner-fix` | LAB / Corner Placement Fix | -12, -7, -2, 0, 0, 0, 0 | Removes the low-end lift a corner or nearby wall adds to the speaker |
| `lab-boom-notch` | LAB / Room Boom Notch | -6, -16, -5, 0, 0, 0, 0 | Deep 250 Hz notch for a one-note room resonance; sweep 125/250 to taste |
| `lab-outdoor` | LAB / Outdoors | 0, -2, -8, -12, -14, -14, -12 | No walls to reinforce the bass, so the rest comes down to rebalance it |
| `lab-tiled-room` | LAB / Tiled Room | -8, -10, -4, 0, -6, -12, -16 | Bathrooms and kitchens: tames boom and the glare hard surfaces add |
| `lab-shelf-fix` | LAB / Shelf / Against Wall | -9, -5, -1, 0, 0, 0, 0 | Milder than the corner fix; for one nearby boundary instead of two |
| `lab-desk-fix` | LAB / Desk Bounce | -4, -10, -4, 0, 0, 0, 0 | Cuts the 250 Hz thickening a desk or table reflects back at you |

#### Genre

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-hiphop-sub` | LAB / Hip-Hop | 0, -2, -10, -14, -14, -12, -9 | Low-end weight with the mids held back so vocals sit on top of the beat |
| `lab-edm-sub` | LAB / EDM | 0, -6, -14, -17, -13, -8, -4 | Bass and top-end sparkle with a deep midrange scoop between them |
| `lab-metal-sub` | LAB / Metal | 0, -3, -12, -14, -8, -6, -8 | Tight low end, scooped low mids, and guitars left with their bite |
| `lab-acoustic-sub` | LAB / Acoustic | -10, -4, 0, 0, -4, -8, -6 | Rumble and harshness removed so guitars and voices stay natural |
| `lab-classical-sub` | LAB / Classical | -8, -3, 0, 0, 0, -3, -8 | Gentle, mostly untouched mids with rumble and top-end edge removed |

#### Single-problem repairs

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-rumble-cut` | LAB / Rumble Cut | -18, -6, 0, 0, 0, 0, 0 | Removes handling, wind, and traffic rumble under the music |
| `lab-driver-protect` | LAB / Driver Protection | -20, -10, -3, 0, 0, 0, 0 | Deep low cut so a small driver stops bottoming out at high volume |
| `lab-honk-cut` | LAB / Honk Cut | 0, 0, -6, -13, -4, 0, 0 | Removes the 1 kHz cupped-hands honk small enclosures add |
| `lab-hiss-cut` | LAB / Hiss Cut | 0, 0, 0, 0, 0, -6, -16 | Drops 8 kHz tape hiss and codec noise without dulling the whole top |

#### Clarity

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-mud-cut` | LAB / Mud Cut | 0, -5, -14, -5, 0, 0, 0 | Clears 500 Hz congestion so voices and guitars stop sounding boxy |
| `lab-harsh-cut` | LAB / Harshness Cut | 0, 0, 0, -2, -13, -7, 0 | Tames the 2-4 kHz shout that makes small speakers tiring to listen to |
| `lab-de-ess` | LAB / De-Ess | 0, 0, 0, 0, -2, -9, -14 | Deep 4-8 kHz cut for recordings with harsh, spitty sibilance |

#### Voice

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-speech-clear` | LAB / Speech Clarity | -16, -9, -2, 1, 0, -4, -11 | Podcasts and audiobooks: removes rumble and hiss around the voice |
| `lab-vocal-forward` | LAB / Vocal Forward | -12, -8, -3, 0, 0, -4, -9 | Brings vocals forward by lowering what surrounds them, not by boosting |

#### Use case

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-gaming-steps` | LAB / Game Footsteps | -16, -12, -4, 0, 0, -2, -10 | Drops explosions and hiss so footsteps and cues sit in front |
| `lab-movie-dialogue` | LAB / Movie Dialogue | -10, -6, 0, 1, 0, -4, -10 | Rumble and effects pulled back so speech stays intelligible at low volume |

#### Dark

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-dark-24` | LAB / Dark 24 | 6, 4, 2, 0, -8, -18, -24 | Extreme upper-frequency reduction with a gently elevated low end |
| `lab-tilt-dark` | LAB / Subtractive Dark | 0, 0, -2, -5, -9, -14, -18 | Warm and relaxed by lowering the top end rather than lifting the bass |

#### Quiet

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-night` | LAB / Night Mode | -22, -12, -3, 0, 0, -2, -5 | Drops the low end that carries through walls; keeps the rest intact |

#### Extreme cuts

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-bass-delete` | LAB / Bass Delete | -24, -18, -12, -6, 0, 3, 6 | Extreme low-frequency reduction for isolation and enclosure tests |

### Boost-based (18)

These lift a band past +6 dB, so they can clip, and the TUI
asks a second time before writing one. They are bench-test curves, not listening
curves. Use very low volume.

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-max-bass` | DANGER / Maximum Bass | 24, 16, 4, -8, -12, -8, -2 | Extreme 125 Hz boost; bench testing only at very low playback volume |
| `lab-bass-cannon` | DANGER / Bass Cannon | 18, 24, 12, -4, -12, -8, 0 | Maximum 250 Hz impact with aggressive low-frequency weight |
| `lab-kick-impact` | DANGER / Kick Impact | 10, 24, 18, 0, -10, -6, 2 | Extreme kick and upper-bass emphasis with carved mids |
| `lab-deep-pressure` | DANGER / Deep Pressure | 24, 12, 0, -10, -14, -8, -2 | Maximum lowest-band pressure with strongly reduced masking bands |
| `lab-extreme-v` | DANGER / Extreme V | 24, 16, -12, -18, -12, 12, 24 | Maximum bass and air around a deeply recessed midrange |
| `lab-hyper-loudness` | DANGER / Hyper Loudness | 18, 10, -8, -12, -6, 10, 18 | Very large low/high lift intended only for low-volume experiments |
| `lab-air-24` | DANGER / Air +24 | -12, -10, -8, 0, 8, 18, 24 | Maximum 8 kHz shelf with progressively reduced low frequencies |
| `lab-clarity-surgery` | DANGER / Clarity Surgery | -10, -12, -16, -4, 12, 20, 16 | Severe low-mid cut and very strong presence/detail emphasis |
| `lab-vocal-megaphone` | DANGER / Vocal Megaphone | -18, -16, -12, 20, 24, 12, -8 | Extreme 1-2 kHz vocal projection with bass suppression |
| `lab-speech-extractor` | DANGER / Speech Extractor | -24, -18, -10, 18, 24, 16, -12 | Maximum speech isolation curve for diagnostic listening |
| `lab-mid-scoop` | DANGER / Mid Scoop | 12, 8, -18, -24, -18, 8, 12 | Deep 500 Hz-2 kHz scoop with elevated frequency extremes |
| `lab-mid-wall` | DANGER / Mid Wall | -12, -8, 12, 24, 20, 4, -8 | Extreme 1-2 kHz emphasis for resonance and intelligibility tests |
| `lab-smile-24` | DANGER / Smile 24 | 24, 16, -8, -16, -8, 16, 24 | Maximum outer-band smile curve with a large center reduction |
| `lab-inverse-smile` | DANGER / Inverse Smile | -24, -16, 8, 16, 8, -16, -24 | Maximum outer-band attenuation and elevated central bands |
| `lab-test-125` | DANGER / 125 Hz +24 | 24, 0, 0, 0, 0, 0, 0 | Single-band maximum boost for controlled bench diagnostics |
| `lab-test-250` | DANGER / 250 Hz +24 | 0, 24, 0, 0, 0, 0, 0 | Single-band maximum boost for controlled bench diagnostics |
| `lab-test-1k` | DANGER / 1 kHz +24 | 0, 0, 0, 24, 0, 0, 0 | Single-band maximum boost for controlled bench diagnostics |
| `lab-test-8k` | DANGER / 8 kHz +24 | 0, 0, 0, 0, 0, 0, 24 | Single-band maximum boost for controlled bench diagnostics |

## My profiles

Edit the gains in the TUI, press `SAVE AS`, name it. It is stored as a seven-point
curve in `%LOCALAPPDATA%\openjbl\profiles.json`, so a profile saved on one speaker
still means something on a model with a different band count.

```powershell
openjbl save-profile --name "Living Room" --pid 20e3 --gains 5 2 0 -1 -2 0 3
openjbl profiles --mine
openjbl delete-profile --key user-living-room
```

Whether a saved curve needs the extended encoder, and whether it needs the
confirmation, are recomputed from its gains every time it loads rather than read
from the file.

## Choosing one

- **At high volume**, start with Balanced or Punch rather than Bass Heavy: every
  boost costs limiter headroom.
- **At low volume**, Loudness is more balanced than lifting the bass alone.
- **For a dark source**, try Crystal Clear before Bright; Bright can turn harsh on
  treble-heavy material.
- **For a boomy room**, LAB / Corner Placement Fix or LAB / Room Boom Notch reach
  far enough to actually fix it; Warm only masks it.
- **For real bass**, LAB / Subtractive Bass and its deeper variants get there
  without distorting. Expect to add volume.
- **Preview everything and start quiet.** Only the Charge 6 is hardware-confirmed;
  every other model rests on static APK evidence alone.
