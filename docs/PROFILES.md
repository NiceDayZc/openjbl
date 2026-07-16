# Curated sound profiles

Profiles are tonal starting points, not amplifier overclocking or limiter bypasses. Seven-point reference curves use 125, 250, 500, 1k, 2k, 4k, and 8kHz. The resolver interpolates in log-frequency space and quantizes the result to the selected model profile:

- Charge 6 and Grip-style: band 1 uses +0.5/-0.75 dB steps; other bands use 0.5 dB.
- General Protocol 4 and legacy parametric: 0.5 dB within -6..+6 dB.
- Simple 3-band and advanced-level: integer values within -6..+6.
- Five-band models use their actual preset frequencies, rather than truncating the seven-band curve.

| Key | Name | Reference curve (125 to 8kHz) | Character |
|---|---|---|---|
| `flat` | Flat / Reference | 0, 0, 0, 0, 0, 0, 0 | No tonal coloration |
| `balanced` | Balanced | 1, .5, 0, 0, 0, .5, 1 | Balanced everyday listening |
| `bass` | Bass Heavy | 6, 4, 1, -1, -1, 0, 1 | Heavy bass with controlled low mids |
| `deep-bass` | Deep Bass | 6, 3, 0, -2, -1, 0, .5 | Deep lows with room for the midrange |
| `punch` | Punch Bass | 4, 5, 2, -1, -1, .5, 1 | Tight, impactful kick |
| `warm` | Warm | 3, 2, 1, .5, 0, -.5, -1 | Smooth and relaxed |
| `loudness` | Low-volume Loudness | 4, 2, 0, -1, 0, 1.5, 3 | Compensates at low listening levels |
| `clear` | Crystal Clear | 0, -1, -2, 0, 2, 3, 4 | Less congestion, more presence and air |
| `bright` | Bright | -.75, -.5, -1, 0, 2, 4, 5 | Opens dark sources |
| `detail` | Detail Monitor | -1.5, -1, -1, 1, 2, 2.5, 2 | Reveals texture and detail |
| `vocal` | Vocal Focus | -.75, -1, -1, 3, 4, 2, 0 | Forward vocals |
| `podcast` | Podcast / Speech | -3, -2, -1, 3, 4, 2, -1 | Clear speech with reduced rumble |
| `acoustic` | Acoustic | 1, 1, .5, 1, 1.5, 2, 2 | String body and detail |
| `rock` | Rock | 4, 3, -1, 1, 3, 3, 2 | Defined kick and guitars |
| `metal` | Metal | 3, 1, -2, 0, 3, 4, 2 | Guitar separation and attack |
| `hip-hop` | Hip-Hop | 6, 4, 0, -1, 1, 2, 3 | Large bass with intelligible vocals and hi-hats |
| `edm` | EDM | 6, 4, -1, -2, 0, 3, 5 | Electronic V-curve |
| `pop` | Pop | 3, 2, 0, 1, 2, 2.5, 3 | Lively, tight, and vocal-forward |
| `jazz` | Jazz | 2, 1, .5, 1, 1, 1.5, 2 | Warm, natural, and ambient |
| `classical` | Classical | 0, 0, -.5, 0, 1, 2, 3 | Placement and air |
| `movie` | Cinema | 5, 3, 0, 1, 3, 2, 3 | Impact, dialogue, and atmosphere |
| `gaming` | Gaming / Footsteps | 0, -1, -2, 0, 4, 5, 2 | Reduces bass masking and emphasizes footsteps |
| `outdoor` | Outdoor | 6, 4, 1, 0, 2, 3, 3 | Compensates for outdoor bass loss |
| `night` | Night / Apartment | -4.5, -3, -1, 1, 2, 1, 0 | Reduces low-frequency wall transmission |

## Selection guidance

- At high volume, start with Balanced or Punch instead of Bass Heavy because multi-band boosts reduce limiter headroom.
- At low volume, Loudness is more balanced than boosting bass alone.
- For a dark source, try Clear before Bright; Bright may become harsh on treble-heavy material.
- For a boomy desk or room, Deep Bass or Night reduces 500Hz-1kHz buildup and vibration more than Warm.
- Preview every profile and begin at low volume. Profiles for models without hardware confirmation rely on static APK evidence only.
