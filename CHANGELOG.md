# Changelog

All notable changes follow Keep a Changelog style. This project uses semantic versioning while its public API stabilizes.

## [0.3.0] - 2026-07-17

### Changed

- **Renamed the project to OpenJBL.** The import package is now `openjbl`, and the console commands are `openjbl` and `openjbl-tui` (previously `vantactl` and `vantatui`).
- **The BLE link is now held open instead of being rebuilt for every frame.** Previously each frame opened and destroyed its own connection -- the CLI even created a fresh event loop per frame -- which made multi-frame writes slow and turned any transient blip into a hard failure. One link per address is now held for the session, matching the Android app, which keeps a single GATT open for its whole process lifetime.
- Notifications are subscribed once per link and left subscribed, as the app does, rather than being re-subscribed and torn down around every transaction.

### Added

- **MY PROFILES**: a third profile tier for curves you make yourself. Edit the gains, press SAVE AS, name it, and it is stored in `profiles.json` next to the config and offered back on every launch. `openjbl save-profile`, `openjbl profiles --mine`, and `openjbl delete-profile` do the same from the CLI. A saved profile is kept as a seven-point tonal curve rather than one speaker's band values, so it still means something on a model with a different band count. Whether a saved curve needs the extended encoder, and whether it needs the extended-gain confirmation, are recomputed from the gains on load rather than trusted from the file -- a hand-edited store cannot talk a +24 dB curve past the confirmation.
- A nine-strong LAB reference family aimed at clean, uncoloured playback: the Harman room curve (Harman's own listener panels -- JBL is Harman -- found people prefer an in-room low shelf under a gentle downward tilt over a literally flat response), a steeper studio tilt, and corrections that take the shop-shelf smiley back off (neutral correction, studio reference, tight bass, detail without glare, silk treble, vocal purity, late-night hi-fi). EQ cannot buy a better driver or more resolution; what it can do is remove colouration, and an expensive speaker is largely defined by that absence -- no port boom, no boxiness, no upper-mid shout, no fake sizzle. Every curve in the family is cuts only and leaves the midrange as the band it protects.
- Thirty-four subtractive LAB profiles, taking the catalog to 87. They spend the extended range on cuts rather than boosts: a ten-strong bass family (tilts from mild to extreme, plus punch, warm, 808, dub, club, basshead and sub-focus), genre curves, placement fixes (corner, shelf, desk, tiled room, outdoors), use-case curves (game footsteps, movie dialogue), and single-problem repairs (rumble, honk, hiss, sibilance, mud, harshness, driver protection). The twenty original LAB profiles all push +18 to +24 dB, which is the one thing the extended range is bad at: a large boost has to come out of the DSP's headroom and the speaker's limiter, so it distorts and then gets quieter. The bass family instead leaves 125 Hz at 0 dB and lowers everything above it -- the tilt is what the ear hears as bass, and a tilt built from cuts costs level, which the volume knob gives back, instead of headroom, which it cannot.
- Automatic setup: one press of SCAN picks the strongest live JBL, connects, verifies the EQ route, and opens the Equalizer. It declines to choose when the signal is too weak or two speakers are within 6 dB, and it never writes.
- Automatic recovery from an unexpected drop: a flat 1 s retry, three attempts, straight to the cached address with no re-scan -- the app's exact strategy. No keepalive is sent, because the app has none.
- A reply demultiplexer built from each SDK command class's own declared response commands, so a push from the speaker can no longer be counted as a write acknowledgement.

### Fixed

- **EQ writes could be acknowledged by an unrelated notification.** Any frame arriving in the timeout window counted as an acknowledgement, so an unsolicited `NOTIFY_EQ_CHANGE` could make an unverified write look verified.
- **Verification authorised an address, not a link.** The probe's connection was already closed before the write opened a new one, so "verified" described a link that no longer existed. It is now bound to the live link's identity and revoked the moment that link drops.
- **A dropped link during a probe was reported as "no supported EQ response"**, blaming the speaker for lacking a capability when the connection had simply died.
- **A programmatically selected model could be paired with the previous model's gains.** `Select.Changed` is posted rather than called, so a chained scan could have written the wrong band shape to real hardware. The write path now resolves its identity once, up front, and never re-reads the widgets.
- The dangerous-profile arm is keyed to the profile and gains it was armed for, so any edit between the two clicks invalidates it instead of a queued event silently clearing it.
- **A hand-typed +24 dB wrote on a single click.** The confirmation was keyed to the selected profile's name, but the gain field is free text, so leaving the tier on STANDARD and typing +24 skipped it entirely on any float-parametric model. It now follows the actual gains. Conversely, the confirmation is no longer demanded for curves that only cut: needing it to apply a -12 dB corner correction was crying wolf, which is what makes people stop reading the real warnings.
- Workers no longer share one exclusive group, so they can no longer cancel each other; a cancelled apply still writes its audit record, and pressing SCAN at launch no longer cancels the update check while its `pip` install keeps running.
- Four UI messages pointed the user at a "CONNECT + VERIFY" button that does not exist.

## [0.2.4] - 2026-07-16

### Fixed

- Locked the Equalizer tab and every EQ control until a live connection and supported EQ response are verified.
- Invalidated the verified target whenever the address/model changes or a read/write connection fails.
- Distinguished live BLE advertisements from cached Windows paired-device metadata and stopped auto-selecting offline cache rows.
- Added a strict post-connect `is_connected` transport check and cleared stale clients after disconnect.
- Replaced theme-colored Footer elements and DataTable/scrollbar accents with deterministic monochrome styling.

## [0.2.3] - 2026-07-16

### Changed

- Added the installed version and release build ID to the always-visible TUI header.
- Added version/build identity to the Activity startup log for support screenshots and diagnostics.

## [0.2.2] - 2026-07-16

### Changed

- Reworked the TUI into a guided Scan, Select, Probe, Tune, Preview, and Apply workflow.
- Replaced Unicode-heavy borders, separators, and curve blocks with legacy-console-safe ASCII.
- Added visible success, warning, and error notifications plus direct `1`/`2`/`3` workspace shortcuts.
- Reduced nested framing and verified the interface at an 80x24 terminal size.
- Added automatic JBL/PID selection from Harman company data, `DFFD`/`FDDF`/`FC69` service data, derived service UUIDs, unique names, and Windows paired-device metadata.
- Replaced the TUI write interlock with direct apply while retaining model and gain validation.
- Added pre-write state capture, write acknowledgement inspection, automatic read-back, per-band delta verification, transaction IDs, detailed Activity evidence, and explicit verified/mismatch/unverified outcomes.
- Added automatic PyPI update checks/installations for TUI users, editable-install protection, and manual `check-update` / `update` CLI commands.

## [0.2.1] - 2026-07-16

### Changed

- Rebranded the distribution, Python package, CLI, TUI, documentation, and repository as VantaDSP (renamed again to OpenJBL in 0.3.0).
- Published the project on PyPI with `pip install vantadsp` as the primary installation path.

## [0.2.0] - 2026-07-16

### Added

- Textual TUI with BLE discovery, model selection, read-only probe, EQ read, packet preview, guarded apply, and privacy-aware audit logging.
- Monochrome workstation layout with detailed system/device/protocol/safety state, live curve display, and 24 curated model-aware sound profiles.
- `profiles` and `set-profile` CLI commands with frequency interpolation and per-model gain quantization.
- PID-based routing across legacy simple, advanced level, legacy parametric, Protocol 4 `0E02`, and Grip-style `0E7F` EQ.
- Persistent local settings, typed package marker, build metadata, CI, lint, typing, security, coverage, and packaging checks.
- Full model coverage matrix and hardware-confirmed Charge 6 profile.

### Safety

- Writes remain dry-run in the CLI and double-confirmed in the TUI.
- APKs, captures, decompiler output, and local audit/config data are excluded from Git.

## [0.1.0] - 2026-07-16

- Initial BLE/SPP transport, packet codecs, model database, CLI, and Charge 6 validation.
