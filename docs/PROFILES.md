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

## Standard (5)

Inside every model's own UI range, so they apply with a single click on any EQ
model. Reach for these at full volume: they shape tone without giving up loudness.

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `flat` | Flat / Reference | 0, 0, 0, 0, 0, 0, 0 | No tonal shaping; use this as a level-checking baseline |
| `balanced` | Balanced | 1, 0.5, 0, 0, 0, 0.5, 1 | Even, fatigue-free tuning with no strongly emphasized range |
| `bass` | Bass Heavy | 6, 4, 1, -1, -1, 0, 1 | Strong 125-250 Hz weight with restrained mids to limit muddiness |
| `vocal` | Vocal Focus | -0.75, -1, -1, 3, 4, 2, 0 | Brings vocals and dialogue forward while reducing masking bass |
| `outdoor` | Outdoor | 6, 4, 1, 0, 2, 3, 3 | Compensates for outdoor bass loss while retaining projection |

## LAB (13)

Beyond the model's UI range. These need `--allow-extended` on the CLI, and only
work on float-parametric models such as the Charge 6 -- a level-index encoder has
no way to express them.

The catalog is curated: one curve per job. Overlapping variants, genre presets
that a reference curve already covers, and the +18 to +24 dB bench-test boosts
were removed. A boost typed into the gain field still works, behind the DANGER
confirmation.

| Key | Name | Curve at 125, 250, 500, 1k, 2k, 4k, 8 kHz | Character |
|---|---|---|---|
| `lab-harman-room` | LAB / Harman Room Curve | 0, -2, -5, -6, -7, -8, -10 | Harman's own preference target: low shelf under a gentle downward tilt |
| `lab-harman-2013` | LAB / Harman Listener Target | 0, -5.5, -4.5, -4.5, -4, -8, -9 | Harman's 2013 listening-test result: solid bass shelf, level mids, treble step |
| `lab-bk-house` | LAB / B&K House Curve | 0, 0, -1, -2, -2.5, -4, -6.5 | The classic 1974 hi-fi room: flat to 160 Hz, then a straight gentle slope |
| `lab-music-studio` | LAB / Music Studio Room | 0, -0.5, -0.5, -0.5, -1, -3, -6.5 | Dolby's music mixing-room curve: flat through the mids, gentle top roll-off |
| `lab-cinema-x` | LAB / Cinema X-Curve | 0, 0, 0, 0, 0, -3.5, -10.5 | The movie-theatre room: full mids, highs rolling off above 2 kHz like a big hall |
| `lab-vocal-bloom` | LAB / Vocal Bloom Room | 0, -2, -1.5, 0, -0.5, -3.5, -7 | A warm, intimate room: bass kept, voices bloom at 1 kHz, soft presence and top |
| `lab-hifi-clarity` | LAB / Hi-Fi Clarity | 0, -6, -7, -4, -5, -5, -3 | Clears the mud and box, keeps the bass, opens the air: clean and transparent |
| `lab-bass` | LAB / Deep Clean Bass | 0, -6, -10.5, -8.5, -8.5, -9, -8 | A 10 dB bass tilt built from cuts, with the 500 Hz mud scooped so it stays tight |
| `lab-vocal` | LAB / Vocal Presence | -7, -0.5, -3, -0.5, 0, -0.5, -0.5 | Singers up front: bass and box pulled back, voice warmth and air untouched |
| `lab-movie` | LAB / Cinema Dialogue | -2, -7.5, -2, 0, 0, -0.5, -4.5 | Clear dialogue that keeps explosion weight: the boomy 250 Hz region removed |
| `lab-speech` | LAB / Podcast & Speech | -19, -5, 0, 0, 0, -0.5, -12.5 | Talk only: rumble and hiss removed, the 500 Hz-3 kHz voice band untouched |
| `lab-gaming` | LAB / Gaming Footsteps | -17.5, -6.5, -3, -2.5, 0, 0, -6.5 | Explosions and rumble pulled down so 2-4 kHz footsteps and cues stand out |
| `lab-night` | LAB / Late Night | -19, -1, -0.5, 0, 0, 0, -1 | Removes the bass that travels through walls; everything above 250 Hz intact |

### The room family

Harman Room Curve is one of several published in-room targets, each the sound of
a particular kind of room. The five after it are the others worth having, laid
over the speaker the same way:

| Room | Source | Shape | Sounds like |
|---|---|---|---|
| Harman Listener Target | Olive, Welti & McMullin, AES 2013 | +6.6 dB below 105 Hz, flat mids, -2.4 dB above 2.5 kHz | Harman with a solid bass shelf and the mids further forward |
| B&K House Curve | Bruel & Kjaer, 1974 | Flat to 160 Hz, straight slope to -6 dB at 20 kHz | A classic hi-fi room; lighter and more open than Harman |
| Music Studio Room | Dolby Atmos Music target | +1 dB below 160 Hz, flat to 1.6 kHz, -1.5 dB/oct to 10 kHz | What the mix engineer heard; the most neutral |
| Cinema X-Curve | SMPTE ST 202, large room | Flat to 2 kHz, -3 dB/oct to 10 kHz, -6 dB/oct above | A movie theatre: full mids, softened highs |
| Vocal Bloom Room | Archimago, 2026 | Bass shelf, +2 dB at 700 Hz-1 kHz, taper from 3 kHz | A warm, intimate club; voices bloom |

They are the target's shape, not a measured room correction: there is no
microphone in the loop, so the speaker's own tuning and your room still add to
whatever the curve does.

### Why these only cut

A large boost has to come from somewhere. It eats the DSP's headroom and runs into
the speaker's limiter, so +24 dB at 125 Hz does not give you more bass: it gives
you distortion, and then less level than you started with.

A cut cannot clip. It costs level, and the volume knob gives that back. Every LAB
curve keeps its loudest band at 0 dB, so turn the volume up after applying one --
by roughly 6-10 dB for Harman Room Curve, Harman Listener Target, Hi-Fi Clarity
and Deep Clean Bass, a few dB for the rest.

### How they were made

Each new LAB curve started as a continuous target response, and its seven gains
were solved for against the filter chain the Charge 6 actually runs: a 125 Hz low
shelf, Q2 peaks at 250 Hz, 500 Hz, 1 kHz, 2 kHz and 4 kHz, and an 8 kHz high
shelf, at 48 kHz (`custom_c2_eq.json`). The gains were then rounded to 0.5 dB.

That step matters because Q2 peaks an octave apart do not join up. A broad cut
built from several of them dips at each centre and rises between them, so the
curve you type is not the response that ships. The table below is the computed
response on the Charge 6, in dB, including the in-between frequencies the seven
numbers hide:

| Profile | 60 | 125 | 250 | 350 | 500 | 700 | 1k | 1.4k | 2k | 2.8k | 4k | 5.6k | 8k | 12k |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Harman Room Curve | -0.1 | -0.3 | -2.7 | -2.6 | -6.0 | -4.1 | -7.5 | -4.9 | -8.6 | -5.4 | -9.4 | -4.8 | -5.9 | -9.1 |
| Harman Listener Target | -0.1 | -0.7 | -6.1 | -3.6 | -5.6 | -3.5 | -5.6 | -3.4 | -5.4 | -4.2 | -9.0 | -4.4 | -5.3 | -8.2 |
| B&K House Curve | -0.0 | -0.0 | -0.1 | -0.4 | -1.3 | -1.1 | -2.4 | -1.7 | -3.1 | -2.2 | -4.6 | -2.5 | -3.6 | -5.9 |
| Music Studio Room | -0.0 | -0.1 | -0.6 | -0.4 | -0.6 | -0.4 | -0.7 | -0.6 | -1.4 | -1.4 | -3.4 | -2.1 | -3.5 | -5.9 |
| Cinema X-Curve | -0.0 | -0.0 | -0.0 | -0.0 | -0.0 | -0.0 | -0.1 | -0.1 | -0.4 | -1.2 | -4.1 | -3.1 | -5.5 | -9.3 |
| Vocal Bloom Room | -0.0 | -0.2 | -2.2 | -1.2 | -1.7 | -0.6 | -0.3 | -0.4 | -0.9 | -1.3 | -3.9 | -2.4 | -3.8 | -6.3 |
| Hi-Fi Clarity | -0.1 | -0.8 | -6.9 | -4.6 | -8.2 | -4.3 | -5.5 | -3.5 | -6.1 | -3.5 | -5.7 | -2.3 | -2.0 | -2.8 |
| Deep Clean Bass | -0.2 | -0.9 | -7.5 | -6.1 | -12.3 | -7.3 | -11.0 | -6.8 | -10.7 | -6.4 | -10.5 | -4.8 | -5.0 | -7.4 |
| Vocal Presence | -6.6 | -3.6 | -1.3 | -1.3 | -3.1 | -1.2 | -0.8 | -0.3 | -0.2 | -0.2 | -0.5 | -0.2 | -0.3 | -0.5 |
| Cinema Dialogue | -2.0 | -1.9 | -7.8 | -3.3 | -2.8 | -1.0 | -0.4 | -0.2 | -0.1 | -0.2 | -0.7 | -0.9 | -2.3 | -4.0 |
| Podcast & Speech | -17.4 | -10.0 | -6.9 | -2.3 | -0.7 | -0.3 | -0.1 | -0.1 | -0.1 | -0.3 | -1.2 | -2.6 | -6.3 | -11.0 |
| Gaming Footsteps | -16.2 | -9.5 | -8.5 | -3.8 | -4.1 | -2.2 | -2.9 | -1.1 | -0.4 | -0.2 | -0.4 | -1.1 | -3.3 | -5.8 |
| Late Night | -17.4 | -9.6 | -2.9 | -1.1 | -0.7 | -0.3 | -0.1 | -0.0 | -0.0 | -0.0 | -0.0 | -0.2 | -0.5 | -0.9 |

The curves that work mostly through the two shelves (the room family except the
Harman Listener Target, Late Night, Podcast & Speech, Vocal Presence, Cinema
Dialogue) land within about 1 dB of their target. The broad mid cuts (both Harman
curves, Hi-Fi Clarity, Deep Clean Bass) carry a 2-3 dB
ripple at 1.4, 2.8 and 5.6 kHz that no choice of gains can remove with this band
layout. On other float-parametric models the same seven-point curve is
interpolated onto that model's own bands.

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

| You want | Use |
|---|---|
| Natural, like a good home speaker | LAB / Harman Room Curve |
| Harman, with more punch and forward mids | LAB / Harman Listener Target |
| A classic, open hi-fi room | LAB / B&K House Curve |
| The mix as the studio heard it | LAB / Music Studio Room |
| Big and smooth, like a cinema | LAB / Cinema X-Curve |
| Warm and intimate, voices blooming | LAB / Vocal Bloom Room |
| Clear and transparent, more air | LAB / Hi-Fi Clarity |
| Bass you feel, without boom | LAB / Deep Clean Bass |
| Singers up front in music | LAB / Vocal Presence |
| Films and series | LAB / Cinema Dialogue |
| Podcasts, audiobooks, talk videos | LAB / Podcast & Speech |
| Hearing footsteps in games | LAB / Gaming Footsteps |
| Late at night, neighbours nearby | LAB / Late Night |
| Maximum volume outdoors or at a party | Outdoor |
| A non-Charge 6 model, or no LAB | Balanced, Bass Heavy, Vocal Focus |

- **Start quiet, then raise the volume.** LAB curves only cut, so they play
  quieter than the speaker's default tuning.
- **Preview everything first.** Only the Charge 6 is hardware-confirmed; every
  other model rests on static APK evidence alone.
